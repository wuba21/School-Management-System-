"""
Utility to generate and compile Amharic (am) translations for SSMS.
Uses polib to create django.po and compile directly to django.mo without external gettext binary.
"""

import os
import sys
from pathlib import Path

try:
    import polib
except ImportError:
    print("Error: polib is not installed.")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / 'locale' / 'am' / 'LC_MESSAGES'
LOCALE_DIR.mkdir(parents=True, exist_ok=True)

PO_FILE = LOCALE_DIR / 'django.po'
MO_FILE = LOCALE_DIR / 'django.mo'

# Comprehensive bilingual translation catalog
TRANSLATIONS = {
    # Navigation & Layout
    "Main": "ዋና",
    "Dashboard": "ዳሽቦርድ",
    "Management": "አስተዳደር",
    "Students": "ተማሪዎች",
    "Teachers": "መምህራን",
    "Academic Years": "የትምህርት ዘመናት",
    "Grades & Sections": "ክፍሎች እና ሴክሽኖች",
    "Subjects": "የትምህርት ዓይነቶች",
    "Class Offerings": "የክፍል ምደባዎች",
    "Curriculum Matrix": "የስርዓተ ትምህርት ማትሪክስ",
    "Academic": "አካዳሚክ",
    "Attendance": "የተማሪዎች መገኘት",
    "Examinations": "ፈተናዎች",
    "Results": "ውጤቶች",
    "Promotion": "የተማሪዎች ዝውውር እና ማለፍ",
    "Timetable": "የክፍል የጊዜ ሰሌዳ",
    "Reports & Analytics": "ሪፖርቶች እና ትንታኔዎች",
    "Analytics Dashboard": "የትንታኔ ዳሽቦርድ",
    "Student Reports": "የተማሪዎች ሪፖርት",
    "Teacher Reports": "የመምህራን ሪፖርት",
    "Attendance Reports": "የመገኘት ሪፖርት",
    "Academic & Exams": "አካዳሚክ እና ፈተናዎች",
    "Promotion & Graduation": "ማለፍ እና ምረቃ",
    "Export Center": "የመረጃ መላኪያ ማዕከል",
    "Intelligence & AI": "ሰው ሰራሽ አስተውሎት (AI)",
    "AI Dashboard": "የ AI ዳሽቦርድ",
    "School Assistant Chat": "የትምህርት ቤት ረዳት ውይይት",
    "Academic Diagnostics": "የአካዳሚክ ምርመራ",
    "Attendance Intelligence": "የመገኘት ትንተና",
    "AI Report Studio": "የ AI ሪፖርት ስቱዲዮ",
    "System": "ስርዓት",
    "User Management": "የተጠቃሚዎች አስተዳደር",
    "Settings": "ቅንብሮች",
    "Backup & Recovery": "የመረጃ ቅጂ እና መልሶ ማግኛ",
    "Audit Logs": "የክትትል ምዝግብ ማስታወሻዎች",
    "Local LAN Mode": "የውስጥ ኔትወርክ (LAN) ሁኔታ",
    "Switch Language": "ቋንቋ ይቀይሩ",
    "System Notifications": "የስርዓት ማሳወቂያዎች",
    "Local School Network": "የአካባቢ ትምህርት ቤት ኔትወርክ",
    "Morning attendance submitted": "የጠዋት መገኘት ተመዝግቧል",
    "Midterm marks entry open": "የግማሽ ዓመት ውጤት መመዝገቢያ ክፍት ነው",
    "Daily backup completed": "የዕለቱ የመረጃ ቅጂ ተጠናቋል",
    "My Profile": "መገለጫዬ",
    "Change Password": "የይለፍ ቃል ቀይር",
    "System Settings": "የስርዓት ቅንብሮች",
    "System Administration": "የስርዓት አስተዳደር",
    "Sign Out": "ውጣ",
    "Sign In": "ግባ",
    "Login": "ግባ",
    "Logout": "ውጣ",

    # Common Actions & Statuses
    "Actions": "እርምጃዎች",
    "Action": "እርምጃ",
    "Status": "ሁኔታ",
    "Active": "ንቁ",
    "Inactive": "ቦዝኗል",
    "Save": "አስቀምጥ",
    "Save Changes": "ለውጦችን አስቀምጥ",
    "Cancel": "ሰርዝ",
    "Delete": "አስወግድ",
    "Edit": "አስተካክል",
    "View": "ተመልከት",
    "Create": "አዲስ ፍጠር",
    "Add": "ጨምር",
    "Submit": "አስገባ",
    "Search": "ፈልግ",
    "Filter": "አጣራ",
    "Reset": "እንደገና ጀምር",
    "Export": "ላክ",
    "Export PDF": "PDF ላክ",
    "Export Excel": "Excel ላክ",
    "Download": "አውርድ",
    "Upload": "ጫን",
    "Print": "አትም",
    "Back": "ተመለስ",
    "Next": "ቀጣይ",
    "Previous": "ቀዳሚ",
    "Confirm": "አረጋግጥ",
    "Yes": "አዎ",
    "No": "አይ",
    "All": "ሁሉም",
    "Total": "ጠቅላላ",
    "Date": "ቀን",
    "Time": "ሰዓት",
    "Description": "መግለጫ",
    "Name": "ስም",
    "Email": "ኢሜይል",
    "Phone Number": "ስልክ ቁጥር",
    "Address": "አድራሻ",
    "Role": "ሚና",
    "Success": "ተሳክቷል",
    "Error": "ስህተት",
    "Warning": "ማስጠንቀቂያ",
    "Info": "መረጃ",

    # Student & Teacher Management
    "Student": "ተማሪ",
    "Teacher": "መምህር",
    "First Name": "ስም",
    "Father's Name": "የአባት ስም",
    "Grandfather's Name": "የአያት ስም",
    "Mother's Name": "የእናት ስም",
    "Gender": "ጾታ",
    "Male": "ወንድ",
    "Female": "ሴት",
    "Date of Birth": "የልደት ቀን",
    "Admission Number": "የመግቢያ ቁጥር",
    "Roll Number": "የመዝገብ ቁጥር",
    "Grade": "ክፍል",
    "Section": "ሴክሽን",
    "Grade Level": "የክፍል ደረጃ",
    "Total Students": "ጠቅላላ ተማሪዎች",
    "Total Teachers": "ጠቅላላ መምህራን",
    "Total Classes": "ጠቅላላ ክፍሎች",
    "Department": "የትምህርት ክፍል",
    "Qualification": "የትምህርት ደረጃ",
    "Specialization": "ሙያዊ ዘርፍ",
    "Employment Date": "የተቀጠሩበት ቀን",

    # Academic & Curriculum
    "Academic Year": "የትምህርት ዘመን",
    "Semester": "መንፈቀ ትምህርት",
    "Semester 1": "1ኛ መንፈቀ ትምህርት",
    "Semester 2": "2ኛ መንፈቀ ትምህርት",
    "Subject": "የትምህርት ዓይነት",
    "Subject Code": "የትምህርት ኮድ",
    "Credit Hours": "የክሬዲት ሰዓት",
    "Periods Per Week": "በሳምንት የክፍለ ጊዜ ብዛት",

    # Attendance
    "Attendance Rate": "የመገኘት ምጣኔ",
    "Average Attendance": "አማካይ መገኘት",
    "Present": "ተገኝቷል",
    "Absent": "ቀርቷል",
    "Late": "አርፍዷል",
    "Excused": "በፈቃድ",
    "Mark Attendance": "መገኘት መዝግብ",
    "Attendance Summary": "የመገኘት ማጠቃለያ",

    # Examinations & Results
    "Examination": "ፈተና",
    "Exam Title": "የፈተና ርዕስ",
    "Exam Type": "የፈተና ዓይነት",
    "Max Score": "ከፍተኛ ውጤት",
    "Weight Percentage": "የክብደት መቶኛ",
    "Score": "ውጤት",
    "Total Score": "ጠቅላላ ውጤት",
    "Average Score": "አማካይ ውጤት",
    "Rank": "ደረጃ",
    "Passing Score": "ማለፊያ ውጤት",
    "Passed": "አልፏል",
    "Failed": "ወድቋል",
    "Pass Rate": "የማለፍ ምጣኔ",
    "Grade Letter": "የውጤት ፊደል",
    "Remarks": "አስተያየት",

    # Promotion
    "Promoted": "አልፏል",
    "Retained": "ተደግሟል",
    "Transferred": "ተዛውሯል",
    "Pending": "በመጠባበቅ ላይ",
    "Promotion Status": "የማለፍ/የዝውውር ሁኔታ",
    "Process Promotion": "የማለፍ ሂደትን ፈጽም",

    # Evaluation Scale
    "Excellent": "እጅግ በጣም ጥሩ",
    "Very Good": "በጣም ጥሩ",
    "Good": "ጥሩ",
    "Satisfactory": "አጥጋቢ",
    "Poor": "ዝቅተኛ",
    "Very Poor": "እጅግ ዝቅተኛ",

    # Reports
    "Report Card": "የትምህርት ማስረጃ (ካርድ)",
    "Student Transcript": "የትምህርት ትራንስክሪፕት",
    "Official Roster": "ኦፊሴላዊ የተማሪዎች መዝገብ (ሮስተር)",
    "Academic Summary": "የአካዳሚክ ማጠቃለያ",
    "Class Roster": "የክፍል መዝገብ",

    # Institution & Location
    "Smart School Management System": "ስማርት የትምህርት ቤት አስተዳደር ስርዓት",
    "Academic Information System (SSMS)": "የአካዳሚክ መረጃ ስርዓት (SSMS)",
    "Majang Zone, Gambella Region, Ethiopia": "ማጃንግ ዞን፣ ጋምቤላ ክልል፣ ኢትዮጵያ",
    "Metti Secondary School": "ሜቲ 2ኛ ደረጃ ትምህርት ቤት",
    "Grades 9-12": "ከ9ኛ እስከ 12ኛ ክፍል",
    "Staff Authentication": "የሰራተኞች ማረጋገጫ (ግባ)",
    "Enter your institutional credentials to access your administrative workspace.": "የስራ ቦታዎን ለማግኘት የተሰጠዎትን የተጠቃሚ ስም እና የይለፍ ቃል ያስገቡ።",
    "Sign In to School Portal": "ወደ ትምህርት ቤት ፖርታል ይግቡ",
    "Remember this terminal": "ይህንን ኮምፒውተር አስታውስ",
    "For account assistance or password resets, contact your School System Administrator.": "የመለያ ድጋፍ ወይም የይለፍ ቃል ዳግም ለማስጀመር፣ የትምህርት ቤቱን የስርዓት አስተዳዳሪ ያነጋግሩ።",
    "Show Password": "የይለፍ ቃል አሳይ",
    "Hide Password": "የይለፍ ቃል ደብቅ",
    "Offline Local LAN Mode": "የውስጥ ኔትወርክ (LAN) ሁኔታ",
    "Ethiopian Calendar": "የኢትዮጵያ ዘመን አቆጣጠር",
    "Gregorian Calendar": "የጎርጎሮሳውያን ዘመን አቆጣጠር",

    # Dashboard & General Analytics
    "Executive Dashboard & Academic Analytics": "የስራ አመራር ዳሽቦርድ እና አካዳሚክ ትንታኔ",
    "Active Classes": "ንቁ ክፍሎች",
    "Today's Attendance": "የዛሬው መገኘት",
    "Pending Exams": "በመጠባበቅ ላይ ያሉ ፈተናዎች",
    "Student Enrollment by Grade Level": "የተማሪዎች ምዝገባ በየክፍል ደረጃ",
    "Attendance Rate Trajectory (%)": "የመገኘት ምጣኔ ሂደት (%)",
    "Overall Attendance Breakdown": "አጠቃላይ የመገኘት ዝርዝር",
    "Student Gender Demographics": "የተማሪዎች የጾታ ስብጥር",
    "Recent Operational Activities": "የቅርብ ጊዜ የስራ እንቅስቃሴዎች",
    "Database Grounded": "ከመረጃ ቋት የተረጋገጠ",
    "Recent Sessions": "የቅርብ ጊዜ ክፍለ ጊዜያት",
    "Current Academic Year": "የአሁኑ የትምህርት ዘመን",
    "Active enrollees": "ንቁ ተማሪዎች",
    "Appointed teachers": "የተመደቡ መምህራን",
    "Sections running": "በስራ ላይ ያሉ ሴክሽኖች",
    "Curriculum cycles": "የትምህርት ዑደቶች",
    "marks recorded": "ውጤቶች ተመዝግበዋል",
    "All Sections": "ሁሉም ሴክሽኖች",
    "Grade Level": "የክፍል ደረጃ",
    "Enrolled": "የተመዘገቡ",
    "Capacity": "አቅም",
    "Cumulative Attendance Compliance:": "አጠቃላይ የመገኘት ተገዢነት:",
    "Male Students": "ወንድ ተማሪዎች",
    "Female Students": "ሴት ተማሪዎች",
    "Teacher Workload Dashboard": "የመምህራን የስራ ጫና ዳሽቦርድ",
    "Record Attendance": "መገኘት መዝግብ",
    "Enter Exam Marks": "የፈተና ውጤት አስገባ",
    "Registrar Operations Panel": "የሬጅስትራር ስራዎች ፓነል",
    "Register New Student": "አዲስ ተማሪ መዝግብ",
    "Generate Transcripts": "ትራንስክሪፕት አውጣ",
    "System Administrator Center": "የስርዓት አስተዳዳሪ ማዕከል",
    "Manage Accounts": "ተጠቃሚዎችን አስተዳድር",
    "View Audit Logs": "የክትትል ምዝግብ ማስታወሻዎችን ተመልከት",
    "Created": "ተፈጥሯል",
    "Updated": "ተሻሽሏል",
    "Auth": "ማረጋገጫ",
    "By:": "በ:",
    "ago": "በፊት",
    "No Student Enrollees Found": "ምንም የተመዘገቡ ተማሪዎች አልተገኙም",
    "No Attendance Sessions Recorded": "ምንም የተመዘገበ የመገኘት ክፍለ ጊዜ የለም",
    "Record Daily Attendance": "የዕለቱን መገኘት መዝግብ",

    # AI Assistant
    "Ask School Assistant": "የትምህርት ቤት ረዳቱን ይጠይቁ",
    "Ask a question in English or Amharic": "ጥያቄዎን በእንግሊዝኛ ወይም በአማርኛ ይጠይቁ",
    "How can I help you today?": "ዛሬ በምን ላግዝዎት እችላለሁ?",
    "Clear Conversation": "ውይይቱን አጽዳ",
    "Send": "ላክ",
    "Thinking...": "በማሰብ ላይ...",
    "AI Recommendations": "የሰው ሰራሽ አስተውሎት ምክሮች",
    "High Risk": "ከፍተኛ ስጋት",
    "Moderate Risk": "መካከለኛ ስጋት",
    "Low Risk": "ዝቅተኛ ስጋት",
    "Normal": "መደበኛ",

    # Redesigned Split Login Experience
    "Welcome to Our School": "እንኳን ወደ ትምህርት ቤታችን በደህና መጡ",
    "Empowering Students Through Quality Education": "ተማሪዎችን በጥራት ትምህርት ማብቃት",
    "Smart School Management and Academic Information System": "ስማርት የትምህርት ቤት አስተዳደር እና የአካዳሚክ መረጃ ስርዓት",
    "Welcome Back": "እንኳን ደህና ተመለሱ",
    "Sign in to access your school account": "የትምህርት ቤት መለያዎን ለመጠቀም ይግቡ",
    "Sign In": "ይግቡ",
    "Signing In...": "በመግባት ላይ...",
    "Remember Me": "አስታውሰኝ",
    "Student Information": "የተማሪዎች መረጃ",
    "Academic Records": "የአካዳሚክ መዝገቦች",
    "Attendance & Timetable": "መገኘት እና የጊዜ ሰሌዳ",
    "Performance Analytics": "የአፈፃፀም ትንታኔ",
    "A comprehensive platform for managing students, teachers, attendance, examinations, academic performance, and school information efficiently.": "ተማሪዎችን፣ መምህራንን፣ መገኘትን፣ ፈተናዎችን፣ የአካዳሚክ አፈፃፀምን እና የትምህርት ቤት መረጃዎችን በብቃት ለማስተዳደር የተዘጋጀ አጠቃላይ ስርዓት።",
    "Need password assistance? Contact the school IT System Administrator.": "የይለፍ ቃል እገዛ ይፈልጋሉ? የትምህርት ቤቱን የአይቲ ሲስተም አስተዳዳሪ ያነጋግሩ።",

    # Grad School Inspired Portal Strings
    "Home": "መነሻ",
    "About School": "ስለ ትምህርት ቤቱ",
    "School Services": "የትምህርት ቤት አገልግሎቶች",
    "Contact": "አድራሻ",
    "ACCESS SCHOOL PORTAL": "ወደ ትምህርት ቤት ፖርታል ይግቡ",
    "STUDENT MANAGEMENT": "የተማሪዎች አስተዳደር",
    "ACADEMIC MANAGEMENT": "የአካዳሚክ አስተዳደር",
    "SCHOOL ADMINISTRATION": "የትምህርት ቤት አስተዳደር",
    "Manage student profiles, registrations, enrollment, and academic history.": "የተማሪዎችን መገለጫ፣ ምዝገባ፣ የክፍል ምደባ እና የአካዳሚክ ታሪክን ማስተዳደር።",
    "Manage subjects, classes, examinations, marks, and academic performance.": "የትምህርት ዓይነቶችን፣ ክፍሎችን፣ ፈተናዎችን፣ ውጤቶችን እና የአካዳሚክ አፈፃፀምን ማስተዳደር።",
    "Support attendance, timetables, reports, and school administration.": "መገኘትን፣ የጊዜ ሰሌዳዎችን፣ ሪፖርቶችን እና የትምህርት ቤት አስተዳደርን መደገፍ።",
    "LOGIN": "ይግቡ",
    "About Our School": "ስለ ትምህርት ቤታችን",
    "Academic Levels (Grades 9–12)": "የትምህርት ደረጃዎች (ከ9ኛ እስከ 12ኛ ክፍል)",
    "Quality Secondary Education": "ጥራት ያለው ሁለተኛ ደረጃ ትምህርት",
    "Faculty & Teaching Staff": "መምህራን እና የማስተማር ሰራተኞች",
    "Offline Local Area Network": "የውስጥ አካባቢያዊ ኔትወርክ (LAN)",
    "Smart School Management and Academic Information System provides a centralized platform for managing student information, teachers, attendance, examinations, academic performance, and school activities.": "ስማርት የትምህርት ቤት አስተዳደር እና የአካዳሚክ መረጃ ስርዓት የተማሪዎችን መረጃ፣ መምህራንን፣ መገኘትን፣ ፈተናዎችን፣ የአካዳሚክ አፈፃፀምን እና የትምህርት ቤት እንቅስቃሴዎችን ለማስተዳደር የተማከለ ስርዓት ያቀርባል።",
    "School Services & Core Modules": "የትምህርት ቤት አገልግሎቶች እና ሞጁሎች",
    "Comprehensive Academic & Administrative Systems": "አጠቃላይ የአካዳሚክ እና አስተዳደራዊ ስርዓቶች",
    "Get In Touch": "ያግኙን",
    "Campus Location & Institutional Contact": "የትምህርት ቤቱ አድራሻ እና የስራ ግንኙነት",
    "School Campus": "የትምህርት ቤት ግቢ",
    "Office & Class Hours": "የቢሮ እና የክፍል ሰዓታት",
    "LAN & Technical Support": "የውስጥ ኔትወርክ (LAN) እና ቴክኒካል ድጋፍ",
    "Access Staff Portal": "የሰራተኞች ፖርታል ይግቡ",
    "Campus Gate & Administrative Office": "የግቢው ዋና በር እና አስተዳደር ቢሮ",
    "Monday – Friday: 8:00 AM – 5:00 PM": "ከሰኞ እስከ አርብ፡ ከጠዋቱ 2:00 - ከሰዓት 11:00",
    "ICT Server Room & IT Support Desk": "የ ICT ሰርቨር ክፍል እና የመረጃ ድጋፍ መስጫ",
}

def generate_catalog():
    po = polib.POFile()
    po.metadata = {
        'Project-Id-Version': 'SSMS 1.0',
        'Report-Msgid-Bugs-To': '',
        'POT-Creation-Date': '2026-11-08 21:00+0300',
        'PO-Revision-Date': '2026-11-08 21:00+0300',
        'Last-Translator': 'SSMS Localization Team <admin@ssms.local>',
        'Language-Team': 'Amharic <am@ssms.local>',
        'Language': 'am',
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=UTF-8',
        'Content-Transfer-Encoding': '8bit',
    }

    for msgid, msgstr in TRANSLATIONS.items():
        entry = polib.POEntry(
            msgid=msgid,
            msgstr=msgstr,
        )
        po.append(entry)

    po.save(str(PO_FILE))
    print(f"[PASS] Saved PO file: {PO_FILE} with {len(po)} entries.")

    po.save_as_mofile(str(MO_FILE))
    print(f"[PASS] Compiled MO file: {MO_FILE} successfully.")

if __name__ == '__main__':
    generate_catalog()
