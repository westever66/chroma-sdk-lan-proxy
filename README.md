# Chroma SDK LAN Proxy

LAN proxy for using the local Razer Chroma REST SDK from Home Assistant,
including the `ha-chroma` personal LAN fork.

The Razer Chroma REST SDK normally listens only on the Windows machine at:

```text
http://localhost:54235/razer/chromasdk
```

After a client initializes a session, the SDK returns another local session URI.
This proxy exposes the bootstrap endpoint and rewrites session responses so
clients on another LAN machine can keep using the returned URI.

## Recommended Setup

Use this on the Windows PC that runs Razer Synapse / Chroma SDK:

```powershell
cd chroma-sdk-lan-proxy
copy .\examples\config.toml "$env:LOCALAPPDATA\ChromaSdkLanProxy\config.toml"
notepad "$env:LOCALAPPDATA\ChromaSdkLanProxy\config.toml"
```

Edit these values to match the Windows PC LAN IP:

```toml
bind_host = "192.168.0.52"
advertise_host = "192.168.0.52"
```

Run manually:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m chroma_sdk_lan_proxy --config "$env:LOCALAPPDATA\ChromaSdkLanProxy\config.toml"
```

Then configure Home Assistant / `ha-chroma` with:

```text
Host: 192.168.0.52
Port: 15435
```

## Autostart

Register a Windows scheduled task that starts the proxy when the current user
logs in:

```powershell
.\scripts\install-autostart.cmd
```

Start it immediately without logging out:

```powershell
Start-ScheduledTask -TaskName "Chroma SDK LAN Proxy"
```

Remove autostart:

```powershell
.\scripts\uninstall-autostart.cmd
```

The default scheduled task waits 30 seconds after login so Razer Synapse has
time to start.

If Windows policy blocks scheduled task creation, the installer falls back to a
current-user Startup folder launcher.

If you prefer calling the PowerShell script directly and Windows blocks script
execution, run this one-time command instead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1
```

## Configuration

Example:

```toml
bind_host = "192.168.0.52"
advertise_host = "192.168.0.52"

public_port = 15435

local_host = "127.0.0.1"
local_port = 54235

session_port_start = 15436
session_port_end = 15499

timeout = 10.0
debug = false

log_file = "%LOCALAPPDATA%/ChromaSdkLanProxy/logs/proxy.log"

# Optional. Set this to the Home Assistant host IP to restrict access.
# allowed_clients = ["192.168.0.66"]
```

CLI options override the config file:

```powershell
python -m chroma_sdk_lan_proxy --config .\config.toml --public-port 15435
```

Print the effective config:

```powershell
python -m chroma_sdk_lan_proxy --config .\config.toml --print-config
```

## Health Check

The main listener exposes:

```text
GET /health
```

Example:

```powershell
Invoke-RestMethod http://192.168.0.52:15435/health
```

It returns whether the proxy can reach the local SDK bootstrap endpoint and
basic session mapping diagnostics.

## Firewall

Allow incoming TCP connections from the Home Assistant host to:

```text
15435
15436-15499
```

For a tighter setup, set `allowed_clients` in the config to the Home Assistant
host IP.

## Development

Run tests:

```powershell
python -m unittest discover -s tests
```

Run the package from source:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m chroma_sdk_lan_proxy --print-config
```
