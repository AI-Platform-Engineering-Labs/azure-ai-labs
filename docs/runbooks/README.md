# Runbooks

| Runbook | Use it to |
|---|---|
| [local-lab.md](local-lab.md) | Run the lab on your laptop with Kind: up, check, change, debug, delete |
| [azure-setup.md](azure-setup.md) | One-time setup before the Azure lab can run (kavrynt-platform foundations, repository variables, quota, lab landing zone, Cloud dev firewall) |
| [azure-lab.md](azure-lab.md) | The three lab workflows in order; create the lab on demand, connect, use the secret store, extend, destroy, fix |

The lab is disposable. Locally, `make lab-down` deletes it. On Azure, the **Azure Lab**
workflow with operation **down**, or the TTL reaper, deletes everything except the
lab landing zone and Key Vault (about USD 4 a month) and kavrynt-platform's foundations.
