# Plan B SaaS — Odoo 19 Development Environment

Complete, runnable local environment for the **Plan B SaaS** product:
a two-server Odoo 19 deployment (one *management* / control-plane server and one
*tenant* server), the two custom add-on repositories, the production database
restored from backup, and a set of scripts that rebuild the whole stack from
scratch.

Everything runs **inside WSL (Ubuntu)**. The repositories live on `D:` so they
stay under git control and are easy to review; the runtime (virtualenv,
databases, filestore, logs) lives on the WSL ext4 filesystem where it is fast.

---

## Table of contents

1. [What the system is](#1-what-the-system-is)
2. [Architecture at a glance](#2-architecture-at-a-glance)
3. [Repository layout](#3-repository-layout)
4. [Runtime layout (WSL)](#4-runtime-layout-wsl)
5. [Prerequisites](#5-prerequisites)
6. [Installation — from scratch](#6-installation--from-scratch)
7. [Starting the system](#7-starting-the-system)
8. [URLs and credentials](#8-urls-and-credentials)
9. [How SaaS provisioning works](#9-how-saas-provisioning-works)
10. [Configuration reference](#10-configuration-reference)
11. [Operational scripts](#11-operational-scripts)
12. [VS Code integration](#12-vs-code-integration)
13. [Troubleshooting](#13-troubleshooting)
14. [Known issues](#14-known-issues)

---

## 1. What the system is

Plan B SaaS sells Odoo as a hosted product. It is made of **two Odoo
instances** that share the same code but serve different databases:

| | **Management server** | **Tenant server** |
|---|---|---|
| Purpose | Control plane: sells and operates subscriptions | Runs the databases that customers actually use |
| Database | `subscribeOne` (single) | `tenant_<company>_<order_id>` (one per customer) |
| Port | `8020` | `8030` |
| Add-ons | `PLan-B-SAAS` + `Plan-B-SAAS-Instance` | `Plan-B-SAAS-Instance` only |
| Database selector | enabled | **disabled** (`list_db = False`) |

The management server never touches a customer database directly. It shells out
to `odoo-bin` to create and populate a tenant database, and then talks to it
over **XML-RPC** to synchronise users, groups and company data.

The two repositories are:

* **`PLan-B-SAAS`** — the *product* code. Contains `subscription_sale`, the
  module that implements packages, sale orders, instances and provisioning.
* **`Plan-B-SAAS-Instance`** — the *per-tenant* code. Contains the modules that
  are installed **inside** every customer database (access control, community
  accounting kit, branding, …).

---

## 2. Architecture at a glance

```
                        ┌───────────────────────────────────────────┐
                        │              WSL (Ubuntu)                 │
   Windows             │                                           │
  ┌──────────┐  HTTP   │   ┌────────────────────────────────────┐   │
  │ Browser  │────────►│   │  Management server   :8020        │   │
  │ / VSCode │  8020   │   │  DB: subscribeOne                   │   │
  └──────────┘         │   │  addons: PLan-B-SAAS + Instance    │   │
                        │   └───────┬────────────────────────────┘   │
                        │           │                                │
                        │           │ 1. subprocess: odoo-bin db init │
                        │           │    odoo-bin -i <modules>       │
                        │           │ 2. XML-RPC (common/object)    │
                        │           │                                │
                        │           ▼                                │
                        │   ┌────────────────────────────────────┐   │
                        │   │  Tenant server       :8030        │   │
                        │   │  DB: tenant_*  (list_db = False)  │   │
                        │   │  addons: Instance repo only        │   │
                        │   └────────────────────────────────────┘   │
                        │                                           │
                        │   ┌────────────────────────────────────┐   │
                        │   │  PostgreSQL 18  (unix socket)     │   │
                        │   │  ~/planb-saas/data/filestore/<db>  │   │
                        │   └────────────────────────────────────┘   │
                        └───────────────────────────────────────────┘
```

Provisioning sequence (all of it inside the management server):

```
sale.order (confirmed, is_saas)
   └─ action_provision()
        ├─ _get_tenant_modules_to_install()   package modules + mandatory modules
        │      └─ _resolve_community_modules()  account → base_accounting_kit + base_account_budget
        ├─ saas.tenant.provisioner.create_database()
        │      └─ odoo-bin db init <tenant_db> --country=EG --language=ar_001
        ├─ saas.tenant.provisioner.install_modules()
        │      └─ odoo-bin -d <tenant_db> -i <modules> --stop-after-init
        ├─ ensure_internal_admin()  one `admin` user, owns base.group_system
        ├─ sync_company_information()  company + portal parameters
        ├─ create_users()  one tenant user per paid slot (XML-RPC)
        ├─ sync_permissions()  planb.tenant.user.slot.sync_from_saas (XML-RPC)
        └─ state = 'running'
```

---

## 3. Repository layout

```
D:\WORK\Plan-B-SAAS-19\
├── PLan-B-SAAS\              git clone — management / product add-ons (8 modules)
│   ├── subscription_sale\        ★ the SaaS product itself
│   ├── login\                    customer login screen (management variant)
│   ├── planb_website\           marketing website
│   ├── self_learning\           e-learning portal
│   ├── dms\                      OCA document management
│   ├── dynamic_accounts_report\
│   ├── edit_branding\
│   └── cybrosys_support_client\
│
├── Plan-B-SAAS-Instance\    git clone — per-tenant add-ons (6 modules)
│   ├── planb_tenant_access\      ★ access control inside tenant databases
│   ├── base_accounting_kit\      community replacement for `account`
│   ├── base_account_budget\
│   ├── custom_url_rewrite\
│   ├── ica_web_responsive\
│   └── login\                    customer login screen (tenant variant, a superset)
│
├── odoo19\                   git clone — upstream Odoo 19.0 (shallow, read-only)
│
├── conf\                    Odoo configuration files (created by this setup)
│   ├── odoo-management.conf
│   └── odoo-tenant.conf
│
├── setup\                   bootstrap / restore / start / stop scripts
│   ├── bootstrap_wsl.sh          creates the virtualenv and installs dependencies
│   ├── restore_database.sh       restores the production backup
│   ├── restore_postprocess.py    rewrites production parameters for local use
│   ├── start_all.sh              starts both servers
│   ├── stop_all.sh               stops both servers
│   ├── status.sh                 shows what is running
│   ├── verify.sh                 runs the full verification suite
│   ├── fix_git_line_endings.sh   normalises CRLF/LF across the repositories
│   ├── install_system_deps.sh    optional OS packages (needs sudo)
│   ├── e2e_provisioning_test.py  end-to-end test of the whole SaaS flow
│   ├── run_e2e_test.sh           runner for the end-to-end test
│   ├── cleanup_e2e_test_data.py  removes what the end-to-end test created
│   └── cleanup_e2e_test_data.sh  runner for the cleanup
│
├── .vscode\                VS Code tasks, settings and debug configurations
│
├── changes\                 markdown log of every change made — read this
│
└── README.md                this file
```

---

## 4. Runtime layout (WSL)

Nothing is installed into the system Python and nothing needs `sudo`:

```
~/planb-saas/
├── venv/                Python 3.14.4 virtualenv with all Odoo 19 requirements
├── data/
│   ├── filestore/
│   │   ├── subscribeOne/      restored filestore of the management database
│   │   └── tenant_*/          one folder per tenant database
│   ├── sessions/              Odoo session files
│   └── addons/                Odoo's own download folder
├── logs/
│   ├── odoo-management.log    structured log of the management server
│   ├── odoo-tenant.log        structured log of the tenant server
│   ├── odoo-management.out    stdout/stderr of the management server
│   └── odoo-tenant.out
├── run/                  PID files (odoo-management.pid, odoo-tenant.pid)
├── restore/              temporary extraction of the backup archive
├── conf/                 runtime copy of the configuration files
└── scripts/
```

**Why the split?** The D: drive is 99 % full (≈ 4.6 GB free), while the WSL
ext4 filesystem has ≈ 948 GB free. Keeping the virtualenv, the filestore and
the extracted backups on ext4 avoids filling the Windows disk and is
noticeably faster. The add-on repositories stay on `D:` because that is where
git tracks them.

---

## 5. Prerequisites

Already satisfied on this machine, listed so the setup can be reproduced:

| Requirement | Version used | Notes |
|---|---|---|
| WSL 2 — Ubuntu | 26.04 | `wsl -d Ubuntu` |
| Python | 3.14.4 | Odoo 19 `requirements.txt` pins 3.14 ("Resolute") explicitly |
| PostgreSQL | 18.6 | already installed in WSL, cluster `18/main`, port 5432 |
| Git | 2.53 | |
| `build-essential`, `libpq-dev`, `python3-dev` | present | needed to compile `psycopg2`, `lxml`, `Pillow` |
| Network access | yes | only needed for `pip install` and `git clone` |

No `sudo` is required by any script in `setup/` except the optional
`install_system_deps.sh`.

> `unzip` is **not** installed in this WSL image, so `restore_database.sh` uses
> `python -m zipfile -e` instead.

---

## 6. Installation — from scratch

Run everything from a WSL terminal.

```bash
cd /mnt/d/WORK/Plan-B-SAAS-19
```

### 6.1 Clone the repositories

```bash
git clone https://github.com/business-sense-corp/PLan-B-SAAS.git
git clone https://github.com/business-sense-corp/Plan-B-SAAS-Instance.git
git clone --branch 19.0 --depth 1 https://github.com/odoo/odoo.git odoo19
```

### 6.2 Create the virtualenv and install every Python dependency

```bash
bash setup/bootstrap_wsl.sh
```

This creates `~/planb-saas/venv` (Python 3.14.4) and installs:

* everything in `odoo19/requirements.txt` — the authoritative Odoo 19 pins,
  including `psycopg2`, `lxml`, `gevent`, `Pillow`, `reportlab`, `Werkzeug`,
  `Babel`, `polib`, `num2words`, `python-ldap`, `passlib`;
* the extra libraries the Plan B add-ons require on top of that:
  `openpyxl`, `ofxparse`, `qifparse`.

Because Ubuntu's Python ships without `ensurepip` and `sudo` is not used, pip is
bootstrapped with `get-pip.py` into the virtualenv.

### 6.3 Normalise the git line endings

```bash
bash setup/fix_git_line_endings.sh
```

See [`changes/06-git-line-endings.md`](changes/06-git-line-endings.md) — without
this step git reports **every** file as modified. The two product
repositories take about half a minute; `odoo19` rewrites 45,729 files and
takes about **twelve minutes**, so let it run to completion.

### 6.4 Restore the production database

```bash
bash setup/restore_database.sh
```

The script is destructive: it drops and recreates the `subscribeOne` database.
It reads the archive from
`/mnt/d/222/subscribeOne_2026-10-20_20-18-30.zip` (override with
`BACKUP_ZIP=...`).

Steps performed:

1. extract the archive into `~/planb-saas/restore` (`dump.sql`, `filestore/`,
   `manifest.json`);
2. drop and recreate the `subscribeOne` database;
3. restore `dump.sql` with `psql -v ON_ERROR_STOP=1`;
4. copy the filestore into `~/planb-saas/data/filestore/subscribeOne`;
5. run `setup/restore_postprocess.py` inside `odoo-bin shell` to reset the
   administrator password and rewrite every production `saas.*` parameter for
   the local machine.

Result of the run on this machine:

```
modules installed : 105
saas instances    : 118
admin user        : admin
```

### 6.5 Optional: system packages

```bash
bash setup/install_system_deps.sh     # needs sudo
```

Installs `wkhtmltopdf` (required to render PDF reports and invoice PDFs) and a
few build helpers. Everything else already works without it.

### 6.6 Start

```bash
bash setup/start_all.sh
```

### 6.7 Verify

```bash
bash setup/verify.sh
```

The verification suite checks every layer — virtualenv, dependencies,
repository cleanliness, PostgreSQL, both HTTP endpoints, XML-RPC
authentication, the restored database content and the server logs — and
prints a line per check:

| Level | Meaning |
|---|---|
| `PASS` | the check succeeded |
| `FAIL` | the **environment** is broken — this fails the script (exit code `1`) |
| `WARN` | a defect in the **Plan B product code** was found — reported, but the exit code stays `0` |
| `SKIP` | the check could not run |

The distinction matters: a defect in the product code must not make a
correctly installed environment look broken. The current result is
**26 passed, 0 failed, 1 warning**, and the full result is documented in
[`changes/09-verification.md`](changes/09-verification.md).

---

## 7. Starting the system

### Everyday use

```bash
bash setup/start_all.sh     # start both servers (background, detached)
bash setup/status.sh        # what is running, which databases exist
bash setup/verify.sh        # full verification suite
bash setup/stop_all.sh      # stop both servers
```

`start_all.sh` waits until each server actually answers an HTTP request, so it
returns only when the UI is usable. The management server needs roughly
**40–120 seconds** to become ready the first time, because Odoo has to import
105 add-on modules from the `D:` drive.

### Manual start (single server, foreground — useful for debugging)

```bash
# management
~/planb-saas/venv/bin/python \
    /mnt/d/WORK/Plan-B-SAAS-19/odoo19/odoo-bin \
    -c /mnt/d/WORK/Plan-B-SAAS-19/conf/odoo-management.conf

# tenant
~/planb-saas/venv/bin/python \
    /mnt/d/WORK/Plan-B-SAAS-19/odoo19/odoo-bin \
    -c /mnt/d/WORK/Plan-B-SAAS-19/conf/odoo-tenant.conf
```

### Updating the add-on code

The add-ons are loaded straight from the repositories — there is no copy step.
After you `git pull` inside `PLan-B-SAAS` or `Plan-B-SAAS-Instance`, restart the
affected server:

```bash
bash setup/stop_all.sh && bash setup/start_all.sh
```

### Adding a new add-on

1. put the module folder into `PLan-B-SAAS` (management) or
   `Plan-B-SAAS-Instance` (tenant);
2. add the repository to `addons_path` in the matching `conf/*.conf` if it is a
   new repository;
3. restart the server and install the module from the Apps menu.

---

## 8. URLs and credentials

| What | URL / value |
|---|---|
| Management UI | <http://localhost:8020/web/login> |
| Management database selector | <http://localhost:8020/web/database/selector> |
| Tenant UI (without a database) | <http://localhost:8030/web/login> → redirects, see below |
| Tenant UI for a specific database | `http://localhost:8030/web/login?db=tenant_<company>_<order_id>` |
| Management XML-RPC | <http://localhost:8020/xmlrpc/2/common> |
| Tenant XML-RPC | <http://localhost:8030/xmlrpc/2/common> |
| Local admin login | `admin` / `admin` |
| Odoo master password | `planb_master_2026` |
| PostgreSQL | unix socket `/var/run/postgresql`, user `softlaptop`, no password |

> **Why `http://localhost:8030/web/login` redirects instead of showing a login
> form.** The tenant server is a multi-database server. Without a `?db=`
> parameter it cannot know which customer database to serve, so Odoo 19
> answers **HTTP 303** and sends you to the database selector — which, because
> `list_db = False`, only says *"The database manager has been disabled by the
> administrator"*. **That is the correct behaviour, not an error.**
>
> A customer is always reached through the URL stored on the instance:
> `http://localhost:8030/web/login?db=tenant_<company>_<order_id>`. The
> management back office shows that link in the instance list.

The `admin` password was reset by `restore_postprocess.py`; the original
production passwords of the other 123 restored users are **unknown** and were
not changed — reset them individually if you need to log in as one of them.
(The restored database has 124 user rows, 121 of them active.)


---

## 9. How SaaS provisioning works

### The data model

| Model | Meaning |
|---|---|
| `saas.module.category` | The **package** (Starter / Growth / Business): price, billing period, included users, modules |
| `saas.package.addon` | Optional paid add-on attached to a package |
| `saas.module` | One installable business module, with `technical_name`, `install_on_every_tenant` and `community_replacement_ids` |
| `sale.order` | A subscription; carries the package, the user count and the billing period |
| `saas.instance` | One tenant database; holds `db_name`, credentials and the `state` machine |
| `saas.instance.user` | One **slot** (licensed user) on the management side, mapped to a tenant user id |
| `saas.subscription.line` | Subscription history (trial / initial / renewal / change) |
| `saas.subscription.change` | Customer-requested plan change |
| `saas.provision.job` | Queue for asynchronous provisioning (cron, every minute) |

`saas.instance.state` values: `draft`, `creating`, `running`, `expired`,
`suspended`, `failed`.

### Tenant database naming

`sale.order._get_database_name_from_company()` builds the name:

```
saas.tenant_db_prefix  +  sanitised company name  +  "_"  +  order id
```

e.g. `tenant_` + `konia` + `_145` → `tenant_konia_145`, truncated to 63
characters in total.

### Tenant module resolution

1. **Package modules** — the `saas.module` records of the selected package.
2. **Mandatory modules** — every active `saas.module` with
   `install_on_every_tenant = True` (currently `login`,
   `ica_web_responsive`, `custom_url_rewrite`, `planb_tenant_access`).
3. **Community replacements** — resolved recursively: `account` is replaced by
   `base_accounting_kit` + `base_account_budget`, so `account` itself is never
   installed in a tenant.

### Two administrators in a tenant

* **Internal Plan B administrator** — `admin`, created by
  `ensure_internal_admin()`. It owns `base.group_system` and is the account the
  management server authenticates with over XML-RPC.
* **Customer administrator** — slot 1, login = the customer's e-mail address.
  It receives `base.group_erp_manager`, `base.group_system` and
  `planb_tenant_access.group_planb_customer_admin`.

Additional slots are called `user2`, `user3`, … and their tenant passwords are
left alone when the management server re-synchronises.

### Access control inside the tenant

`planb_tenant_access` (module `planb.tenant.user.slot`) receives the module
list and the slot list from the management server through
`sync_from_saas()` and then:

* creates/updates one `planb.tenant.module.access` per licensed module,
* creates/updates one `planb.tenant.user.slot` per licensed user,
* deactivates slots that are no longer paid for,
* recomputes each user's groups from the modules the customer bought.

---

## 10. Configuration reference

### `conf/odoo-management.conf`

| Option | Value | Why |
|---|---|---|
| `dbfilter` | `^subscribeOne$` | the management server may only serve the management database |
| `list_db` | `True` | the database selector is available (single database) |
| `addons_path` | odoo core → `Plan-B-SAAS-Instance` → `PLan-B-SAAS` | **order matters**, see below |
| `data_dir` | `~/planb-saas/data` | filestore and sessions on the fast ext4 filesystem |
| `http_port` | `8020` | |
| `workers` | `0` | WSL has only ≈ 3.8 GB RAM; two servers must fit |
| `max_cron_threads` | `0` | no background jobs while developing |
| `admin_passwd` | `planb_master_2026` | Odoo master password (database manager) |
| `db_password` | *omitted* | PostgreSQL is reached over the unix socket with peer authentication |

### `conf/odoo-tenant.conf`

| Option | Value | Why |
|---|---|---|
| `dbfilter` | `^tenant_` | only tenant databases are served here |
| `list_db` | `False` | **no** database selector → a customer cannot list or discover another customer's database |
| `addons_path` | odoo core → `Plan-B-SAAS-Instance` | the tenant must not load the management modules |
| `http_port` | `8030` | |
| `admin_passwd` | `planb_master_2026` | |

`list_db = False` hides the `/web/database/selector` and the
`/web/database/*` manager routes. A tenant is still reachable through
`?db=tenant_x`, because Odoo 19's `db_filter()` does not consult `list_db`.

### The `login` module name collision

Both repositories ship a module named `login`. They are **not** interchangeable:

| | `PLan-B-SAAS/login` | `Plan-B-SAAS-Instance/login` |
|---|---|---|
| `models/ir_ui_menu.py` | identical | identical |
| `views/login_templates.xml` | identical | identical |
| `views/custom_page_title.xml` | identical | identical |
| `controllers/portal.py` | — | **only here** (`/planb/customer_portal`) |
| `static/src/js/user_menu.js` | — | **only here** ("Customer Portal" menu entry) |
| `__manifest__.py` | — | **adds** the `web.assets_backend` bundle for `user_menu.js` |

The Instance variant is a strict superset. Odoo resolves a module by scanning
`addons_path` in order, so **`Plan-B-SAAS-Instance` must come first** — which is
what both configuration files do. Reversing the order would silently remove the
customer portal from the tenant login screen.

### `saas.*` system parameters

These live in the management database (`ir.config_parameter`) and are edited
from *Settings → SaaS* (`res.config.settings` in `saas_config.py`).

| Parameter | Local value | Purpose |
|---|---|---|
| `saas.odoo_host` | `http://localhost:8020` | public URL of the management portal |
| `saas.tenant_public_url` | `http://localhost:8030` | URL opened by customers |
| `saas.tenant_internal_url` | `http://127.0.0.1:8030` | URL used by the management server for XML-RPC |
| `saas.tenant_python_bin` | `~/planb-saas/venv/bin/python` | interpreter used for the tenant commands |
| `saas.tenant_odoo_bin` | `…/odoo19/odoo-bin` | Odoo entry point used for the tenant commands |
| `saas.tenant_config_path` | `…/conf/odoo-tenant.conf` | configuration used for the tenant commands |
| `saas.tenant_db_prefix` | `tenant_` | prefix of every tenant database |
| `saas.tenant_admin_login` | `admin` | internal administrator inside the tenant |
| `saas.tenant_admin_password` | `admin` | password of that administrator |
| `saas.default_admin_password` | `admin` | password handed to new customers |
| `saas.tenant_command_timeout` | `1800` | timeout of the `odoo-bin` subprocess, in seconds |
| `saas.tenant_rpc_timeout` | `120` | timeout of the XML-RPC calls, in seconds |
| `web.base.url` | `http://localhost:8020` | base URL used in generated links |

---

## 11. Operational scripts

All scripts live in `setup/` and are run from WSL.

| Script | Needs sudo | What it does |
|---|---|---|
| `bootstrap_wsl.sh` | no | creates `~/planb-saas/venv` and installs every Python dependency |
| `restore_database.sh` | no | **destructive** — drops and recreates `subscribeOne` from the backup |
| `restore_postprocess.py` | no | piped into `odoo-bin shell`; resets passwords and rewrites parameters |
| `start_all.sh` | no | starts the tenant server, then the management server, and waits until both answer HTTP |
| `stop_all.sh` | no | `SIGTERM`, then `SIGKILL` after 30 s; removes the PID files |
| `status.sh` | no | servers, PID, HTTP status, databases, virtualenv, last log lines |
| `verify.sh` | no | runs the full verification suite (environment → PostgreSQL → servers → XML-RPC → data → logs); `FAIL` = environment problem, `WARN` = product defect |
| `fix_git_line_endings.sh` | no | sets `core.autocrlf=input` and normalises the working tree to LF |
| `install_system_deps.sh` | **yes** | `wkhtmltopdf` and build helpers |
| `run_e2e_test.sh` | no | runs the end-to-end provisioning test (see [`changes/09-verification.md`](changes/09-verification.md)) |
| `cleanup_e2e_test_data.sh` | no | removes every record and database the end-to-end test created |

Every script honours these environment variables:

| Variable | Default |
|---|---|
| `PLANB_RUNTIME_DIR` | `~/planb-saas` |
| `PLANB_ODOO_SRC` | `/mnt/d/WORK/Plan-B-SAAS-19/odoo19` |
| `PLANB_MGMT_CONF` | `…/conf/odoo-management.conf` |
| `PLANB_TENANT_CONF` | `…/conf/odoo-tenant.conf` |
| `PLANB_ADMIN_PASSWORD` | `admin` |
| `BACKUP_ZIP` | `/mnt/d/222/subscribeOne_2026-10-20_20-18-30.zip` |
| `DB_NAME` | `subscribeOne` |

---

## 12. VS Code integration

The workspace contains a `.vscode/` folder:

* **`tasks.json`** — one task per operation (restore, start, stop, status,
  logs). `Ctrl+Shift+B` runs the default build task, which is *start both
  servers*; every task is a WSL task, so it runs inside Ubuntu.
* **`settings.json`** — makes WSL the default terminal profile.
* **`launch.json`** — debug configurations that attach the Python debugger to
  the two Odoo servers.

Open the folder in VS Code, then:

1. `Ctrl+Shift+P` → **WSL: Connect to WSL** (or open a terminal and pick the
   *Ubuntu* profile);
2. `Ctrl+Shift+B` to start both servers;
3. `Ctrl+Shift+P` → **Tasks: Run Task** → `logs: management` to follow the log.

If the terminal is not WSL by default: `Ctrl+Shift+P` → *Terminal: Select
Default Profile* → **Ubuntu (WSL)**.

---

## 13. Troubleshooting

**The management server takes a long time to answer the first request.**
Expected. Odoo imports 105 add-on modules from the `D:` drive; the first boot
takes 60–90 seconds, later boots are much faster because the OS caches the
files. `start_all.sh` already waits for a real HTTP response.

**`could not translate host name "..."`**
The management server must resolve itself. Use `127.0.0.1` / `localhost`, not
the machine name.

**`FATAL: database "subscribeOne" does not exist`**
Run `bash setup/restore_database.sh`.

**`psycopg2.OperationalError: ... FATAL: role "odoo" does not exist`**
The configuration must not contain a `db_user` other than `softlaptop`, and
`db_password` must be **omitted** (peer authentication over the unix socket).
Writing `db_password = False` makes Odoo log a warning and still use a
password.

**A tenant database is not reachable.**
The tenant server only serves databases whose name matches `^tenant_`. Check
`dbfilter` in `conf/odoo-tenant.conf`.

**`http://localhost:8030/web/login` shows "The database manager has been
disabled by the administrator".**
Expected. Without a `?db=` parameter the tenant server does not know which
customer database to serve and redirects to the database selector, which is
disabled by design. Use the instance URL from the management back office:
`http://localhost:8030/web/login?db=tenant_<company>_<order_id>`.

**The management log contains `Could not get content for
planb_website/static/src/js/contact_form.js`.**
That file is referenced by `planb_website/__manifest__.py` but was never
committed to the repository — a known product defect, not a problem with this
installation. See [`changes/08-known-issues.md`](changes/08-known-issues.md) §11.

**`Module not found` during provisioning.**
The tenant `addons_path` must contain every module of the installation plan.
`Plan-B-SAAS-Instance` holds all tenant-side modules.

**The XML-RPC endpoint logs a deprecation warning.**
Expected. Odoo 19 still serves `/xmlrpc/2` and `/jsonrpc`, but logs
`The /xmlrpc, /xmlrpc/2 and /jsonrpc endpoints are deprecated in Odoo 19 and
scheduled for removal in Odoo 22`. The SaaS code still uses XML-RPC, so this
warning is expected until that code is migrated to JSON-RPC.

**Git reports every file as modified.**
Run `bash setup/fix_git_line_endings.sh`.

---

## 14. Known issues

**Twelve** product defects were found during the installation and
**deliberately not fixed** — patching them here would make the local system
behave differently from production. The full write-up, with the reproduction
and the proposed patch for each, is in
[`changes/08-known-issues.md`](changes/08-known-issues.md).

| # | Issue | Severity |
|---|---|---|
| 1 | `saas_config.py` still contains the developer path `/home/mohamed/workspace/odoo19/...` as the *default* of `saas.tenant_odoo_bin` and `saas.tenant_config_path`. It is overridden in this environment, but the default is wrong for every other machine — and on a freshly created database (no restore, no post-processing) **every provisioning attempt fails**. | High |
| 2 | Two seeded `saas.module` records — *Data Migration* and *Extra Training Hour* — carry a literal label in `technical_name` instead of a module name. They are part of the *Starter* package. Odoo 19 does **not** fail on them: it logs `invalid module names, ignored` and silently skips them, so the tenant is created and invoiced **without** the two modules the customer paid for. A third defect in the same table: rows 14 and 15 are duplicates of `planb_tenant_access`, and the model's unique constraint on `technical_name` is not enforced in the restored database, so the module appears twice in the mandatory list. | High |
| 3 | `base_account_budget` has a `post_init_hook` that adds **every** internal tenant user to the *Analytic Accounting* group at install time. | Medium |
| 4 | `saas.master_password` defaults to `admin`, and the value stored in the restored database is the placeholder `1`. The field is written but never read by the provisioning code. | Medium |
| 5 | The tenant group list hardcodes `point_of_sale.group_pos_manager`, which does not resolve in a tenant that has no `point_of_sale`. The provisioning still succeeds — only the POS-manager right is skipped — but every tenant logs the warning. | Medium |
| 6 | The XML-RPC dependency will break when Odoo 22 removes the endpoint. It is the transport the whole product uses to administer tenants. | Medium |
| 7 | `Plan-B-SAAS-Instance` has 168 compiled `.pyc` files committed to git. A `.gitignore` was added during this setup, but the already-committed files were left in place. | Low |
| 8 | Six models still use the `_sql_constraints` attribute, which Odoo 19 deprecates. The constraints still apply; the syntax will be removed. | Low |
| 9 | The product passes `--without-demo=all` to the tenant installer; Odoo 19 expects a boolean and logs a warning. The behaviour is still correct. | Low |
| 10 | The 118 restored `saas.instance` records point at tenant databases that were never part of the backup, so *Sync* fails on them. Not a defect — a property of the backup. | Info |
| 11 | `planb_website/__manifest__.py` lists `planb_website/static/src/js/contact_form.js`, but **that file was never committed to the repository**. The website bundle is still built and served, but the build logs an `ERROR` and substitutes a `console.error(...)` placeholder — so the contact-form enhancement is silently missing. | Medium |
| 12 | Asking the tenant server over XML-RPC for a tenant database that does not exist returns a fault that contains the **full Python traceback**, including the absolute path of the installation. | Medium |

