# Runbooks

| Runbook | Use it to |
|---|---|
| [local-lab.md](local-lab.md) | Run the lab on your laptop with Kind: up, check, change, debug, delete |
| [azure-setup.md](azure-setup.md) | One-time setup before the Azure lab can run (landing zone, repository variables, quota) |
| [azure-lab.md](azure-lab.md) | Create the Azure lab on demand, connect to it, extend it, destroy it, fix it |

The lab is disposable. Locally, `make lab-down` deletes it. On Azure, the **Azure Lab**
workflow with operation **down**, or the TTL reaper, deletes everything except the
landing-zone foundations, which cost about nothing.
