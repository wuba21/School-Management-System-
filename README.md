# Smart School Management and Academic Information System (SSMS)

An AI-powered, offline-first School Management and Academic Information System designed specifically for secondary schools operating in local area network (LAN) environments.

Tailored for **Majang Zone Secondary School, Gambella Region, Ethiopia** (Grades 9–12, 1,000–2,000 students, 20+ laboratory computers, no internet dependency).

---

## 🚀 Technology Stack

* **Backend Framework:** Python 3.14 & Django 6.1
* **Database:** PostgreSQL (with SQLite support for initial local development)
* **Database Driver:** `psycopg` 3 (with binary drivers)
* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5
* **Configuration:** `python-dotenv` (.env management)
* **Deployment Target:** Windows Server / Windows 10 Host on School Local Area Network (LAN)

---

## 📂 Project Architecture & Applications

The project is structured into modular Django applications:

| Application | Purpose | Status |
| :--- | :--- | :---: |
| **`core`** | Base templates, global CSS/JS, and shared utilities | **Active** |
| **`accounts`** | User authentication and role-based access control (RBAC) | Registered |
| **`academics`** | Academic years, semesters, grades 9–12, sections, streams, and subjects | Registered |
| **`students`** | Student registration (three-part names), profiles, and enrollments | Registered |
| **`teachers`** | Teacher profiles, qualifications, and subject/section allocations | Registered |
| **`timetable`** | Weekly schedule management and conflict detection | Registered |
| **`attendance`**| Daily and period-based attendance grids with absence alerting | Registered |
| **`examinations`**| Assessment weighting, exam timetables, and grading rules | Registered |
| **`results`** | Mark entry, score validation (0–100), averages, and class ranks | Registered |
| **`reports`** | Printable PDF report cards, section broadsheets, and transcripts | Registered |
| **`dashboard`** | Role-tailored dashboards for Principal, Registrar, Teacher, SysAdmin | Registered |
| **`ai_assistant`**| Scikit-learn predictive risk analysis and offline school assistant | Registered |

---

## 🛠️ Installation & Setup Instructions

Follow these beginner-friendly Windows PowerShell instructions to set up and run the project:

### 1. Open Windows PowerShell in the Project Directory
```powershell
Set-Location -Path "D:\SmartSchoolManagementSystem"
```

### 2. Activate the Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```
*(If you encounter a script execution restriction error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

### 3. Verify Dependencies
Dependencies are listed in `requirements.txt`. If setting up on a new machine, install with:
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` if not already present:
```powershell
Copy-Item .env.example .env
```
Inside `.env`, configure your database credentials:
* Set `DB_ENGINE=sqlite3` for initial testing.
* Set `DB_ENGINE=postgresql` once your PostgreSQL server is installed and running.

### 5. Run Database Migrations
```powershell
python manage.py migrate
```

### 6. Start the Development Server
```powershell
python manage.py runserver
```

To make the server accessible to other computers on the school's local network (LAN):
```powershell
python manage.py runserver 0.0.0.0:8000
```

### 7. Access the Application
* **Home Page:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Django Admin:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 📑 Project Documentation Index

* 📄 [PROJECT_OVERVIEW.md](file:///d:/SmartSchoolManagementSystem/PROJECT_OVERVIEW.md)
* 📄 [FUNCTIONAL_REQUIREMENTS.md](file:///d:/SmartSchoolManagementSystem/FUNCTIONAL_REQUIREMENTS.md)
* 📄 [NON_FUNCTIONAL_REQUIREMENTS.md](file:///d:/SmartSchoolManagementSystem/NON_FUNCTIONAL_REQUIREMENTS.md)
* 📄 [USER_ROLES.md](file:///d:/SmartSchoolManagementSystem/USER_ROLES.md)
* 📄 [SYSTEM_ARCHITECTURE.md](file:///d:/SmartSchoolManagementSystem/SYSTEM_ARCHITECTURE.md)
* 📄 [DEVELOPMENT_ROADMAP.md](file:///d:/SmartSchoolManagementSystem/DEVELOPMENT_ROADMAP.md)
