# SSMS LAN DEPLOYMENT & OPERATING MANUAL
## Smart School Management and Academic Information System (SSMS)
### Metti Secondary School — Godere Woreda, Majang Zone, Gambella Region, Ethiopia
---

**Document Code:** SSMS-MAN-2026-V1  
**Target Audience:** School Principal, System Administrator, IT Officer, Registrar, and Teachers  
**Environment:** 100% Offline Local Area Network (LAN) / Edge Server (No Internet Dependency)  
**System Architecture:** Windows Edge Server + PostgreSQL + Waitress WSGI + WhiteNoise + Bootstrap 5 Offline  

---

## 1. SYSTEM OVERVIEW & TOPOLOGY

The Smart School Management and Academic Information System (SSMS) is engineered to run in an offline-first, high-availability architecture tailored for Metti Secondary School. The system operates continuously even during internet outages or complete regional telecom blackouts.

```
                  ┌──────────────────────────────────────────────┐
                  │             SCHOOL EDGE SERVER               │
                  │   - Windows 10/11 Pro or Windows Server      │
                  │   - PostgreSQL 16 Service (Port 5432)        │
                  │   - Waitress Multi-threaded WSGI (Port 8000) │
                  │   - Static IP: e.g., 192.168.1.100           │
                  └──────────────────────┬───────────────────────┘
                                         │
                   Ethernet Switch / School Wi-Fi Access Point
                                         │
        ┌────────────────────────┬───────┴────────────────┬────────────────────────┐
        │                        │                        │                        │
┌───────▼────────┐      ┌────────▼───────┐      ┌─────────▼───────┐      ┌─────────▼───────┐
│ Principal PC   │      │ Registrar PC   │      │ Staffroom Laptop│      │ Teacher Tablet  │
│ 192.168.1.101  │      │ 192.168.1.102  │      │ 192.168.1.103   │      │ 192.168.1.104   │
└────────────────┘      └────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## 2. PRE-REQUISITES & INITIAL SETUP

### 2.1 Hardware Requirements
- **Edge Server PC:** Dedicated desktop or workstation with:
  - Processor: Intel Core i5 / AMD Ryzen 5 or higher
  - RAM: 8 GB minimum (16 GB recommended)
  - Storage: 256 GB SSD minimum
  - Power: Uninterruptible Power Supply (UPS) with at least 30–60 minutes battery backup
- **Network Equipment:**
  - 8-port or 16-port Gigabit Ethernet Switch
  - Cat6 Ethernet cables connecting office desktops
  - Secure Wi-Fi Access Point for mobile teacher laptops and tablets
- **Storage Media:**
  - Two (2) 64 GB or 128 GB external USB flash drives for off-server backups

### 2.2 Server Static IP Assignment
To ensure client machines always know where to find the server:
1. Open Windows **Settings** > **Network & Internet** > **Ethernet** (or Wi-Fi).
2. Click **Edit** IP assignment and select **Manual** (IPv4).
3. Set:
   - **IP Address:** `192.168.1.100` (or appropriate school subnet address)
   - **Subnet Mask:** `255.255.255.0`
   - **Gateway:** `192.168.1.1` (school router IP)
   - **DNS:** Leave blank or set `192.168.1.1`

---

## 3. DAILY OPERATIONS & SERVER MANAGEMENT

### 3.1 Starting the Server
To launch the SSMS server for the school day:
1. Turn on the School Edge Server PC and log into Windows.
2. Ensure PostgreSQL service is running (starts automatically with Windows).
3. Open the project folder (`D:\SmartSchoolManagementSystem`).
4. **Double-click:** `START_SSMS_SERVER.bat`
5. A console window will appear displaying:
   ```
   [OK] .env file found
   [OK] Django system check passed
   [OK] Static files collected
   [OK] Database migrations applied
   SSMS is now running. Access it from any computer on the school LAN:
     http://<server-ip>:8000/
   ```
6. **Keep this window open** during school hours. Minimizing it is fine.

### 3.2 Stopping the Server
At the end of the school day or before powering down the server:
- Option A: Press `Ctrl + C` inside the server console window.
- Option B: Double-click `STOP_SSMS_SERVER.bat`.

---

## 4. NETWORK CLIENT ACCESS (STAFF WORKSTATIONS)

Staff do not install any software. They only need a modern web browser (Google Chrome, Microsoft Edge, or Mozilla Firefox).

### 4.1 URL for All Workstations
In the browser address bar, type:
```
http://192.168.1.100:8000/
```
*(Replace `192.168.1.100` with the actual server IP).*

### 4.2 Browser Bookmarking & Desktop Shortcut
1. In Chrome / Edge, navigate to `http://192.168.1.100:8000/`.
2. Click the star icon to bookmark the page as **"Metti SSMS"**.
3. To place a shortcut on the Windows Desktop:
   - Click browser menu `...` > **More tools** > **Create shortcut...**
   - Check **"Open as window"** to run SSMS like a standalone desktop app.

---

## 5. FIREWALL & NETWORK CONFIGURATION

If client computers receive `ERR_CONNECTION_TIMED_OUT`:
1. On the Edge Server PC, right-click `scripts\configure_firewall.bat`.
2. Select **"Run as administrator"**.
3. This creates an inbound Windows Defender Firewall rule for TCP Port `8000`.

---

## 6. BACKUP & DISASTER RECOVERY PROTOCOL

### 6.1 Automated Daily Backups
1. On the Edge Server PC, right-click `scripts\schedule_daily_backup.bat`.
2. Select **"Run as administrator"**.
3. A Windows Scheduled Task named `SSMS_Daily_Backup` will be registered to run every day at **18:00 (6:00 PM)**.
4. Backups are saved in `backups\database\` and `backups\media\`.

### 6.2 Manual USB Offsite Backup (Weekly SOP)
Every Friday afternoon, the IT Officer or Registrar must copy backups to an external USB:
1. Log into SSMS as Administrator or Principal.
2. Go to **System Administration** > **Backup Management** (`/backups/`).
3. Insert USB Flash Drive labeled **"Metti SSMS Backup A"** (alternate with B weekly).
4. Click **"Export to USB"** or select the latest `.sqlite3.gz` / `.sql.gz` and click **"Download"**.
5. Save the file to the USB drive.
6. Hand the USB drive to the School Principal to be stored in the office fireproof safe.

---

## 7. USER ROLES & ACCESS MATRIX

| Role | Default Access | Scope of Authority |
|---|---|---|
| **System Administrator (ADMIN)** | Full administrative access | Server health, user creation, password reset, backups, audit logs, system configuration. |
| **Principal (PRINCIPAL)** | School-wide academic oversight | Approves term marks, approves transfer/leaving certificates, views school analytics, overrides promotion. |
| **Registrar (REGISTRAR)** | Student admissions & records | Student registration, section enrollment, ID card batch generation, certificate drafting. |
| **Teacher (TEACHER)** | Classroom-level access | Takes attendance for assigned sections, enters continuous assessment marks for assigned subjects. |

---

## 8. TROUBLESHOOTING GUIDE

| Issue | Likely Cause | Solution |
|---|---|---|
| **Client cannot connect (`ERR_CONNECTION_REFUSED`)** | Server not running | Run `START_SSMS_SERVER.bat` on the server PC. |
| **Client cannot connect (`ERR_CONNECTION_TIMED_OUT`)** | Windows Firewall blocking port 8000 | Run `scripts\configure_firewall.bat` as Administrator on server. |
| **IP address changed after reboot** | DHCP router changed server IP | Assign a static IP to server PC in Windows network adapter settings. |
| **"Account Locked Out" message on login** | 5 consecutive wrong passwords | Wait 15 minutes or ask System Admin to clear failed attempts via Admin console. |
| **Cannot generate PDF / Blank screen** | Pop-up blocker in browser | Allow pop-ups for `http://192.168.1.100:8000` in browser settings. |
| **Server sluggish / high CPU** | Too many concurrent export jobs | Waitress is configured with 8 threads; adjust in `serve_lan.py` if server has more CPU cores. |

---

*Metti Secondary School — Godere Woreda, Majang Zone, Gambella Region, Ethiopia.*  
*Smart School Management and Academic Information System (SSMS).*
