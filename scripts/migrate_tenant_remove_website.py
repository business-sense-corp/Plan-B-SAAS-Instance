#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plan B SaaS - Tenant Website Module Removal Tool (Ticket BS-0034)
==================================================================
Opt-in migration script to safely inspect and remove the unintended 'website'
module and its auto-install bridge modules from existing tenant databases.

Usage:
    python3 migrate_tenant_remove_website.py -d <tenant_db>               # Dry-run (default)
    python3 migrate_tenant_remove_website.py --all-tenants                # Dry-run on all tenants
    python3 migrate_tenant_remove_website.py -d <tenant_db> --apply       # Execute removal with backup
"""

import argparse
import datetime
import os
import subprocess
import sys

# Standard auto-install bridge modules that can be safely uninstalled alongside website
SAFE_WEBSITE_MODULES = {
    'website',
    'website_mail',
    'website_payment',
    'website_sms',
    'website_crm',
    'website_crm_sms',
    'website_crm_livechat',
    'website_livechat',
    'website_mass_mailing',
    'website_mass_mailing_sms',
    'website_links',
    'website_project',
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Safely inspect and remove 'website' from customer tenants."
    )
    parser.add_argument(
        "-c", "--config",
        default="/mnt/d/WORK/Plan-B-SAAS-19/conf/odoo-tenant.conf",
        help="Path to Odoo configuration file."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-d", "--database",
        help="Specific tenant database name (e.g. tenant_acme_123)."
    )
    group.add_argument(
        "--all-tenants",
        action="store_true",
        help="Process all databases matching 'tenant_' prefix."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the uninstallation. If omitted, runs in DRY-RUN mode."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip database backup before uninstallation (NOT recommended)."
    )
    parser.add_argument(
        "--backup-dir",
        default="/home/softlaptop/planb-saas/backups",
        help="Directory to save pre-migration database dumps."
    )
    return parser.parse_args()


def get_tenant_databases(conf_path):
    import psycopg2
    # Connect via local unix socket
    conn = psycopg2.connect(
        dbname="postgres",
        host="/var/run/postgresql",
        port=5432,
        user="softlaptop",
    )
    with conn.cursor() as cr:
        cr.execute("SELECT datname FROM pg_database WHERE datname LIKE 'tenant_%' ORDER BY datname;")
        dbs = [r[0] for r in cr.fetchall()]
    conn.close()
    return dbs


def take_backup(db_name, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{db_name}_pre_website_removal_{ts}.dump")
    print(f"[*] Creating backup: {backup_path}...")
    cmd = [
        "pg_dump",
        "-h", "/var/run/postgresql",
        "-U", "softlaptop",
        "-F", "c",
        "-b",
        "-v",
        "-f", backup_path,
        db_name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Backup failed: {res.stderr}")
    print(f"[+] Backup successfully created ({os.path.getsize(backup_path) / 1024 / 1024:.2f} MB)")
    return backup_path


def audit_tenant(env, db_name):
    # Ensure module dependency graph in DB reflects latest manifests on disk
    try:
        env['ir.module.module'].update_list()
    except Exception as e:
        print(f"    [!] Note: update_list warning on {db_name}: {e}")

    Module = env['ir.module.module']
    website_mod = Module.search([('name', '=', 'website'), ('state', '=', 'installed')], limit=1)
    if not website_mod:
        return {
            'db_name': db_name,
            'has_website': False,
            'can_remove': True,
            'installed_website_modules': [],
            'blocking_modules': [],
        }

    # Find all installed modules that depend on website
    installed = Module.search([('state', '=', 'installed')])
    installed_website_mods = []
    blocking_mods = []

    for m in installed:
        if m.name == 'website' or 'website' in [d.name for d in m.dependencies_id]:
            installed_website_mods.append(m.name)
            if m.name not in SAFE_WEBSITE_MODULES:
                blocking_mods.append(m.name)

    return {
        'db_name': db_name,
        'has_website': True,
        'can_remove': len(blocking_mods) == 0,
        'installed_website_modules': sorted(installed_website_mods),
        'blocking_modules': sorted(blocking_mods),
    }


def uninstall_website(env, db_name, modules_to_remove):
    print(f"[*] Uninstalling {len(modules_to_remove)} module(s) on {db_name}: {modules_to_remove}...")
    Module = env['ir.module.module']
    mods = Module.search([('name', 'in', modules_to_remove), ('state', '=', 'installed')])
    if mods:
        mods.button_immediate_uninstall()
    print(f"[+] Modules uninstalled successfully on {db_name}.")


def main():
    args = parse_args()

    # Setup Odoo environment
    sys.path.insert(0, "/mnt/d/WORK/Plan-B-SAAS-19/odoo19")
    import odoo
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry

    odoo.tools.config.parse_config(["-c", args.config])

    if args.database:
        databases = [args.database]
    else:
        databases = get_tenant_databases(args.config)

    print("=" * 70)
    print(" Plan B SaaS - Tenant Website Removal Tool (Ticket BS-0034)")
    print(f" Mode: {'[APPLY - LIVE]' if args.apply else '[DRY-RUN - SIMULATION]'}")
    print(f" Target Databases: {len(databases)} database(s)")
    print("=" * 70)

    for db_name in databases:
        print(f"\n>>> Checking database: {db_name}")
        try:
            registry = Registry(db_name)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                result = audit_tenant(env, db_name)

                if not result['has_website']:
                    print(f"    [OK] 'website' is NOT installed on {db_name}. No action needed.")
                    continue

                print(f"    [!] 'website' is INSTALLED on {db_name}.")
                print(f"    [i] Active website-related modules: {', '.join(result['installed_website_modules'])}")

                if not result['can_remove']:
                    print(f"    [ERROR] CANNOT safely remove website from {db_name}!")
                    print(f"    Blocking business modules found: {', '.join(result['blocking_modules'])}")
                    print("    These modules are part of the customer package/addons and require website.")
                    continue

                if not args.apply:
                    print(f"    [DRY-RUN] Would uninstall: {', '.join(result['installed_website_modules'])}")
                    print("    [DRY-RUN] No changes were made. Use --apply to execute.")
                else:
                    if not args.no_backup:
                        backup_path = take_backup(db_name, args.backup_dir)

                    uninstall_website(env, db_name, result['installed_website_modules'])
                    cr.commit()

                    # Verify removal
                    with registry.cursor() as verify_cr:
                        verify_env = api.Environment(verify_cr, SUPERUSER_ID, {})
                        rem_mod = verify_env['ir.module.module'].search([
                            ('name', '=', 'website'),
                            ('state', '=', 'installed')
                        ])
                        if not rem_mod:
                            print(f"    [SUCCESS] 'website' and bridge modules successfully removed from {db_name}!")
                        else:
                            print(f"    [WARNING] 'website' still appears installed on {db_name}.")

        except Exception as e:
            print(f"    [ERROR] Failed processing {db_name}: {e}")

    print("\n" + "=" * 70)
    print(" Complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
