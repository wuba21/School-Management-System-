# Non-Functional Requirements Specification

Non-functional requirements describe how the system operates rather than specific behaviors. They define criteria regarding security, performance, reliability, usability, and local network operations suitable for a secondary school in Majang Zone, Gambella, Ethiopia.

---

## 1. Security Requirements

* **NFR-SEC-01 (Password Hashing):** All user passwords must be hashed using Django's default cryptographic hasher (`PBKDF2PasswordHasher` with SHA-256 iterations) with salt. Plain-text passwords must never be stored, logged, or displayed.
* **NFR-SEC-02 (CSRF Protection):** All HTTP POST, PUT, and DELETE forms must include Cross-Site Request Forgery (CSRF) tokens validated by Django middleware.
* **NFR-SEC-03 (XSS Prevention):** All user input rendered on the user interface must be sanitized and HTML-escaped by Django's templating engine to prevent Cross-Site Scripting (XSS).
* **NFR-SEC-04 (SQL Injection Prevention):** Database access must strictly use Django's Object-Relational Mapping (ORM) parameterized queries. Raw SQL with manual string concatenation is strictly prohibited.
* **NFR-SEC-05 (Session Security):** Sessions must be configured with `SESSION_COOKIE_HTTPONLY = True` to prevent client-side JavaScript access to session identifiers.
* **NFR-SEC-06 (Protection of Sensitive Data):** Student medical notes, disciplinary records, and staff personal contact details must only be visible to authorized roles (Principal, Registrar, and SysAdmin).

---

## 2. Performance Requirements

* **NFR-PERF-01 (LAN Response Time):** Standard administrative pages (student search, mark entry forms, attendance lists) must load within **1.5 seconds** over a 100 Mbps or 1 Gbps local Ethernet LAN.
* **NFR-PERF-02 (Concurrent Users):** The local server must comfortably support at least **30 to 50 concurrent active users** (teachers entering marks simultaneously in computer labs during end-of-term grading periods) without server crashes or memory exhaustion.
* **NFR-PERF-03 (Database Query Optimization):** All queries fetching related models (e.g., student enrollments with student details, marks with subjects) must use `select_related` and `prefetch_related` to eliminate the N+1 query problem.
* **NFR-PERF-04 (Pagination):** All large lists (students, attendance logs, audit entries) must enforce server-side pagination with default page sizes of 25 to 50 records per page.
* **NFR-PERF-05 (Report Generation Throughput):** Bulk generation of semester report cards for an entire section (up to 60 students) must complete within **10 seconds**.

---

## 3. Reliability and Data Integrity

* **NFR-REL-01 (ACID Compliance):** The database must be PostgreSQL, providing full ACID (Atomicity, Consistency, Isolation, Durability) transactional integrity for all grade, attendance, and enrollment operations.
* **NFR-REL-02 (Atomic Transactions):** Critical multi-step operations (such as end-of-year promotion processing or bulk mark uploads) must be wrapped in `transaction.atomic()`. If an error occurs midway, all changes must roll back completely without leaving partial data.
* **NFR-REL-03 (Data Consistency Constraints):** Database-level foreign keys, unique constraints (e.g., unique student ID, unique enrollment per student per academic year), and check constraints (e.g., marks between 0 and 100) must be enforced at both the model and database schema levels.
* **NFR-REL-04 (Fault Tolerance):** If power is suddenly interrupted to the server computer, the PostgreSQL write-ahead log (WAL) must guarantee that committed data is preserved without corruption.

---

## 4. Usability and UI/UX Design

* **NFR-USE-01 (Design Aesthetic):** The interface must be clean, modern, and uncluttered:
  * White or light-gray backgrounds (`#f8f9fa`, `#ffffff`) for readability in well-lit classrooms.
  * Professional accent colors (deep navy `#1a365d`, slate blue `#2b6cb0`, subtle emerald green `#2f855a`).
  * No loud, distracting animations or nonfunctional decorative elements.
* **NFR-USE-02 (Navigation Simplicity):** Clear, collapsible sidebar navigation with intuitive icons. Users should be able to access any core task in **3 clicks or fewer** from their dashboard.
* **NFR-USE-03 (Immediate Feedback):** Every form submission must provide clear visual feedback:
  * Green alert banners for successful operations (e.g., *"Attendance recorded successfully for Grade 10-B"*).
  * Red alert banners detailing exact input validation errors.
* **NFR-USE-04 (Print-Friendly Layouts):** Report cards, transcripts, student rosters, and timetables must include clean CSS print stylesheets (`@media print`) so they format cleanly on standard A4 paper without displaying website navigation bars or action buttons.
* **NFR-USE-05 (Responsive Layout):** The user interface must display properly across desktop monitors, laptops, and tablets (screen resolutions from 1024x768 up to 1920x1080).

---

## 5. Maintainability and Code Quality

* **NFR-MAINT-01 (Modular Architecture):** The Django codebase must be decomposed into focused, loosely coupled apps (e.g., `accounts`, `academics`, `students`, `attendance`, `examinations`, `reports`, `ai_engine`, `audit`).
* **NFR-MAINT-02 (Coding Standards):** All Python code must strictly follow **PEP 8** style guidelines, including descriptive variable names and clear docstrings explaining business logic.
* **NFR-MAINT-03 (Comprehensive Documentation):** Setup guides, database schemas, and API routes must be documented in clear Markdown files within the repository.
* **NFR-MAINT-04 (Automated Testing):** Every critical app must include automated unit and integration tests (using `django.test.TestCase`) covering models, forms, permissions, and calculations. Minimum target code coverage for business logic: **80%**.

---

## 6. Offline LAN Operation

* **NFR-LAN-01 (Zero External Dependencies):** The system must not make external HTTP requests or depend on Content Delivery Networks (CDNs) for static resources.
  * Bootstrap 5 CSS and JavaScript files must be stored locally in the Django `static/` directory.
  * Chart.js and icons must be bundled locally.
  * Web fonts must be self-hosted locally (using standard system fonts or locally served `.woff2` files).
* **NFR-LAN-02 (Local IP Binding):** The application server must be capable of binding to `0.0.0.0` and responding to requests addressed to the host machine's static LAN IP address (e.g., `http://192.168.1.100:8000`).
* **NFR-LAN-03 (Browser Compatibility):** Client computers running standard modern web browsers (Google Chrome, Mozilla Firefox, Microsoft Edge) connected to the LAN must access the system without installing any client software.

---

## 7. Data Backup, Archiving, and Disaster Recovery

* **NFR-BAK-01 (Automated Daily Backups):** The system shall include an automated scheduled script (or one-click administrative command) that produces a compressed PostgreSQL database dump (`.sql.gz` or custom format) once every 24 hours.
* **NFR-BAK-02 (External Drive Mirroring):** The backup system must support saving copies to a secondary physical storage drive (e.g., an external USB drive plugged into the server) to safeguard against primary hard drive failure.
* **NFR-BAK-03 (Disaster Recovery Time Objective - RTO):** In the event of complete server failure, a system administrator following the documented recovery manual must be able to restore the full system on a replacement computer within **30 minutes**.
* **NFR-BAK-04 (Recovery Point Objective - RPO):** Data loss in the event of an unforeseen hardware failure must not exceed **24 hours** of data entry.
