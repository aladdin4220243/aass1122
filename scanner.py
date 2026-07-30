import smtplib
import dns.resolver
import socket
import concurrent.futures
import threading
import time
from datetime import datetime
from tqdm import tqdm
import os
import random
import pickle
from pathlib import Path
import shutil # Added for file operations
import shlex # Added for quoting paths in shell commands
from google.colab import files # Added for upload and download
import subprocess # Added for robust shell command execution

# Install necessary libraries (included here as per request)


# ============================================
# الإعدادات
# ============================================
MAX_WORKERS = 10000
BATCH_SIZE = 100000
SOCKET_TIMEOUT = 5
REQUEST_DELAY = 0.05

class GmailVerifier:
    """فحص جميع ملفات مجلد disabled"""

    def __init__(self):
        self.timeout = SOCKET_TIMEOUT
        self.delay = REQUEST_DELAY
        socket.setdefaulttimeout(self.timeout)

        # خوادم MX
        self.mx_servers = [
            'gmail-smtp-in.l.google.com',
            'alt1.gmail-smtp-in.l.google.com',
            'alt2.gmail-smtp-in.l.google.com',
            'alt3.gmail-smtp-in.l.google.com',
            'alt4.gmail-smtp-in.l.google.com'
        ]

        # المسار الرئيسي
        self.base_path = "orgenal folder"
        self.disabled_folder = os.path.join(self.base_path, 'disabled')

        # إنشاء المجلدات
        self.create_folders()

        # إحصائيات
        self.stats = {
            'total': 0, 'live': 0, 'new_disabled': 0,
            'invalid': 0, 'error': 0, 'processed': 0,
            'files_processed': 0, 'total_files': 0
        }

        # أقفال
        self.stats_lock = threading.Lock()
        self.file_lock = threading.Lock()
        # مسارات الملفات
        self.live_file = os.path.join(self.base_path, 'live', '12345Noah Brookslive_accounts.txt')
        self.new_disabled_file = os.path.join(self.base_path, 'new_disabled', 'new_disabled_accounts.txt')
        self.invalid_file = os.path.join(self.base_path, 'invalid', '12345Noah Brooksinvalid_accounts.txt')
        self.processed_file = os.path.join(self.base_path, 'processed', 'processed_accounts.txt')
        self.log_file = os.path.join(self.base_path, 'logs', f'session_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

        # تحميل الحسابات المفحوصة
        self.processed_emails = self.load_processed()

    def create_folders(self):
        """إنشاء جميع المجلدات"""
        folders = [
            self.base_path,
            os.path.join(self.base_path, 'live'),
            self.disabled_folder,
            os.path.join(self.base_path, 'new_disabled'),
            os.path.join(self.base_path, 'invalid'),
            os.path.join(self.base_path, 'processed'),
            os.path.join(self.base_path, 'logs')
        ]

        print("\n" + "="*70)
        print("📁 إنشاء المجلدات")
        print("="*70)

        for folder in folders:
            Path(folder).mkdir(parents=True, exist_ok=True)
            print(f"   ✅ {folder}/")

        print("="*70)

    def get_all_disabled_files(self):
        """الحصول على جميع ملفات txt في مجلد disabled"""
        if not os.path.exists(self.disabled_folder):
            return []

        txt_files = []
        for file in os.listdir(self.disabled_folder):
            if file.endswith('.txt'): # Ensure we only read .txt files
                file_path = os.path.join(self.disabled_folder, file)
                txt_files.append(file_path)

        return sorted(txt_files)  # ترتيب أبجدي

    def load_processed(self):
        """تحميل الحسابات المفحوصة"""
        processed = set()
        if os.path.exists(self.processed_file):
            try:
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    processed = {line.strip().lower() for line in f if line.strip()}
                print(f"📂 تم تحميل {len(processed):,} حساب مفحوص سابقاً")
            except Exception as e:
                print(f"⚠️ خطأ في تحميل المفحوصة: {e}")
        return processed

    def save_processed(self, email):
        """حفظ حساب مفحوص"""
        try:
            with self.file_lock:
                with open(self.processed_file, 'a', encoding='utf-8') as f:
                    f.write(f"{email}\n")
        except:
            pass

    def load_emails_from_file(self, file_path):
        """تحميل الإيميلات من ملف محدد"""
        emails = []
        try:
            file_name = os.path.basename(file_path)
            print(f"\n📄 قراءة الملف: {file_name}")

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # فلترة
            valid = []
            for line in lines:
                email = line.strip().lower()
                if email and '@' in email and email.endswith('@gmail.com'):
                    valid.append(email)

            # إزالة التكرار داخل الملف
            unique = list(dict.fromkeys(valid))

            if len(valid) > 0:
                print(f"   📊 {len(unique):,} حساب صالح (من أصل {len(lines):,} سطر)")
                if len(valid) != len(unique):
                    print(f"   🔄 تم إزالة {len(valid)-len(unique):,} مكرر")

            return unique

        except Exception as e:
            print(f"   ❌ خطأ: {e}")
            return []

    def verify_email(self, email, mx_server):
        """فحص حساب واحد"""
        server = None
        try:
            server = smtplib.SMTP(timeout=self.timeout)
            server.connect(mx_server, 25)
            server.helo('gmail.com')
            server.mail('verify@gmail.com')

            code, message = server.rcpt(email)
            server.quit()

            if code == 250:
                return 'live', "نشط"
            elif code == 550:
                msg = str(message).lower()
                if 'disabled' in msg or 'user disabled' in msg:
                    return 'new_disabled', "لا يزال معطل"
                else:
                    return 'invalid', "غير موجود"
            else:
                return 'error', f"كود {code}"

        except Exception as e:
            return 'error', str(e)[:30]
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

    def save_result(self, email, status):
        """حفظ النتيجة"""
        try:
            if status == 'live':
                filepath = self.live_file
            elif status == 'new_disabled':
                filepath = self.new_disabled_file
            elif status == 'invalid':
                filepath = self.invalid_file
            else:
                return

            with self.file_lock:
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(f"{email}\n")
        except:
            pass

    def worker(self, email_chunk, mx_server, pbar):
        """عامل الفحص"""
        for email in email_chunk:
            try:
                if email in self.processed_emails:
                    pbar.update(1)
                    continue

                status, message = self.verify_email(email, mx_server)

                if status in ['live', 'new_disabled', 'invalid']:
                    self.save_result(email, status)

                    with self.stats_lock:
                        self.stats[status] += 1
                        self.stats['processed'] += 1
                        self.processed_emails.add(email)

                    self.save_processed(email)
                else:
                    with self.stats_lock:
                        self.stats['error'] += 1
                        self.stats['processed'] += 1

                pbar.update(1)
                time.sleep(self.delay)

            except Exception:
                with self.stats_lock:
                    self.stats['error'] += 1
                    self.stats['processed'] += 1
                pbar.update(1)

    def verify_files(self):
        """فحص جميع الملفات في مجلد disabled"""

        # الحصول على جميع الملفات
        all_files = self.get_all_disabled_files()
        self.stats['total_files'] = len(all_files)

        if not all_files:
            print(f"\n❌ لا توجد ملفات txt في: {self.disabled_folder}")
            print("📝 ضع ملفاتك في هذا المجلد")
            return False

        print(f"\n{'='*70}")
        print(f"📁 تم العثور على {len(all_files)} ملف في مجلد disabled/")
        print(f"{'='*70}")

        for i, file_path in enumerate(all_files, 1):
            file_name = os.path.basename(file_path)
            print(f"   {i:2d}. {file_name}")

        print("="*70)

        # تجميع كل الإيميلات من جميع الملفات
        all_emails = []
        files_processed = 0

        for file_path in all_files:
            file_emails = self.load_emails_from_file(file_path)
            if file_emails:
                all_emails.extend(file_emails)
                files_processed += 1

            self.stats['files_processed'] = files_processed

        if not all_emails:
            print("\n❌ لا توجد إيميلات صالحة في أي ملف!")
            return False

        # إزالة التكرار بين الملفات
        total_before = len(all_emails)
        all_emails = list(dict.fromkeys(all_emails))
        duplicates_across_files = total_before - len(all_emails)

        print(f"\n📊 إجمالي الإيميلات قبل إزالة التكرار: {total_before:,}")
        print(f"🔄 تم إزالة {duplicates_across_files:,} مكرر بين الملفات")
        print(f"✅ إجمالي الإيميلات الفريدة: {len(all_emails):,}")

        # بدء الفحص
        self.verify_all_emails(all_emails)
        return True

    def verify_all_emails(self, emails):
        """فحص قائمة الإيميلات"""

        print(f"\n{'='*70}")
        print(f"🚀 بدء الفحص - {len(emails):,} حساب فريد")
        print(f"{'='*70}\n")

        # تصفية المفحوص سابقاً
        new_emails = [e for e in emails if e not in self.processed_emails]
        print(f"📊 جديد للفحص: {len(new_emails):,}")
        print(f"📁 التصنيف:")
        print(f"   📂 live/         - حسابات أصبحت نشطة")
        print(f"   📂 new_disabled/ - حسابات لا تزال معطلة")
        print(f"   📂 invalid/      - حسابات غير موجودة")
        print("-" * 70)

        if not new_emails:
            print("✅ جميع الحسابات مفحوصة!")
            return

        # تقسيم إلى دفعات
        batches = [new_emails[i:i+BATCH_SIZE] for i in range(0, len(new_emails), BATCH_SIZE)]

        self.stats['start_time'] = time.time()
        self.stats['total'] = len(new_emails)

        for batch_num, batch in enumerate(batches, 1):
            print(f"\n📦 دفعة {batch_num}/{len(batches)} - {len(batch):,}")

            mx_server = random.choice(self.mx_servers)
            chunk_size = max(1, len(batch) // MAX_WORKERS)
            chunks = [batch[i:i+chunk_size] for i in range(0, len(batch), chunk_size)]

            with tqdm(total=len(batch), desc="⚡ فحص", unit="حساب") as pbar:
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = [
                        executor.submit(self.worker, chunk, mx_server, pbar)
                        for chunk in chunks
                    ]
                    concurrent.futures.wait(futures)

            # إحصائيات سريعة
            elapsed = time.time() - self.stats['start_time']
            speed = self.stats['processed'] / elapsed if elapsed > 0 else 0

            print(f"\n📊 بعد الدفعة {batch_num}:")
            print(f"   ✅ Live: {self.stats['live']:,}")
            print(f"   🔒 New Disabled: {self.stats['new_disabled']:,}")
            print(f"   ❌ Invalid: {self.stats['invalid']:,}")
            print(f"   ⚡ {speed:.1f}/ثانية")

        self.stats['end_time'] = time.time()

    def show_final_stats(self):
        """عرض الإحصائيات النهائية"""
        elapsed = self.stats['end_time'] - self.stats['start_time'] if 'end_time' in self.stats and self.stats['end_time'] else 0

        print("\n" + "="*70)
        print("🏆 النتائج النهائية")
        print("="*70)

        print(f"\n📁 الملفات المعالجة: {self.stats['files_processed']} من {self.stats['total_files']}")
        print(f"\n📊 التصنيف النهائي:")
        print(f"   ✅ Live (أصبحت نشطة)        : {self.stats['live']:,}")
        print(f"   🔒 New Disabled (لا تزال معطلة): {self.stats['new_disabled']:,}")
        print(f"   ❌ Invalid (غير موجودة)     : {self.stats['invalid']:,}")
        print(f"   ⚠️  Errors                  : {self.stats['error']:,}")
        print(f"   📊 الإجمالي                 : {self.stats['processed']:,}")

        if elapsed > 0:
            print(f"\n⚡ السرعة: {self.stats['processed']/elapsed:.2f} حساب/ثانية")

        print("\n📁 ملفات النتائج:")
        print(f"   📂 {self.live_file}")
        print(f"   📂 {self.new_disabled_file}")
        print(f"   📂 {self.invalid_file}")
        print("="*70)

    def generate_report(self):
        """توليد تقرير نهائي"""
        report_file = os.path.join(self.base_path, 'logs', f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("📊 تقرير فحص مجلد disabled\n")
            f.write("="*80 + "\n\n")

            f.write(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📁 المسار: {self.disabled_folder}\n\n")

            f.write(f"📁 الملفات المعالجة: {self.stats['files_processed']} من {self.stats['total_files']}\n\n")

            f.write("📈 إحصائيات التصنيف:\n")
            f.write(f"   ✅ Live (أصبحت نشطة)        : {self.stats['live']:,}\n")
            f.write(f"   🔒 New Disabled (لا تزال معطلة): {self.stats['new_disabled']:,}\n")
            f.write(f"   ❌ Invalid (غير موجودة)     : {self.stats['invalid']:,}\n")
            f.write(f"   ⚠️  Errors                  : {self.stats['error']:,}\n")
            f.write(f"   📊 الإجمالي                 : {self.stats['processed']:,}\n\n")

            if self.stats['processed'] > 0:
                f.write("📊 النسب المئوية:\n")
                f.write(f"   Live          : {(self.stats['live']/self.stats['processed']*100):.2f}%\n")
                f.write(f"   New Disabled  : {(self.stats['new_disabled']/self.stats['processed']*100):.2f}%\n")
                f.write(f"   Invalid       : {(self.stats['invalid']/self.stats['processed']*100):.2f}%\n\n")

            # قائمة الملفات المصدر
            f.write("📋 الملفات المصدر:\n")
            all_files = self.get_all_disabled_files()
            for i, file_path in enumerate(all_files, 1):
                file_name = os.path.basename(file_path)
                f.write(f"   {i:2d}. {file_name}\n")

        print(f"\n📄 التقرير: {report_file}")

# ============================================n# التنفيذ (Combined Workflow)
# ============================================

def main_workflow():
    print("\n" + "="*80)
    print("🔥 GMAIL VERIFIER - فحص جميع ملفات مجلد disabled")
    print("="*80)
    print("📁 المصدر: orgenal folder/disabled/ (جميع ملفات .txt)")
    print("📂 النتائج: live | new_disabled | invalid")
    print("="*80)

    # 1. Setup target directory for uploads
    target_upload_dir = "/content/orgenal folder/disabled/"
    !mkdir -p "{target_upload_dir}"
    print(f"\nCreated target upload directory: {target_upload_dir}")

    # 2. Upload files
    print("\nPlease select the files you wish to upload (e.g., your .txt account files and any .zip files):")
    uploaded = files.upload()

    uploaded_zip_files = []
    for filename in uploaded.keys():
        source_path = os.path.join("/content/", filename)
        destination_path = os.path.join(target_upload_dir, filename)
        shutil.move(source_path, destination_path)
        print(f'User uploaded file "{filename}" moved to "{destination_path}"')
        if filename.endswith('.zip'):
            uploaded_zip_files.append(destination_path)

    # 3. Unzip all uploaded .zip files
    if uploaded_zip_files:
        for zip_file_path in uploaded_zip_files:
            print(f"\nUnzipping {zip_file_path}...")
            try:
                # Use subprocess.run for robust command execution
                unzip_cmd = ["unzip", "-o", zip_file_path, "-d", target_upload_dir]
                print(f"Executing: {' '.join([shlex.quote(arg) for arg in unzip_cmd])}")
                subprocess.run(unzip_cmd, check=True, capture_output=True, text=True)

                # Remove the zip file after unzipping
                os.remove(zip_file_path)
                print(f"✅ {zip_file_path} unzipped and removed.")
            except subprocess.CalledProcessError as e:
                print(f"❌ Error unzipping {zip_file_path}: {e.stderr.strip()}")
            except FileNotFoundError:
                print(f"❌ Error: The zip file '{zip_file_path}' was not found during unzipping.")
            except Exception as e:
                print(f"❌ An unexpected error occurred during unzipping {zip_file_path}: {e}")
    else:
        print("\nNo .zip files found to unzip in the target directory.")

    # 4. Create the verifier and run the verification
    verifier = GmailVerifier()
    if verifier.verify_files():
        verifier.show_final_stats()
        verifier.generate_report()

    # 5. Zip the result files
    base_path_for_zip = 'orgenal folder' # Use relative path as it worked previously
    live_file = os.path.join(base_path_for_zip, 'live', '12345Noah Brookslive_accounts.txt')
    new_disabled_file = os.path.join(base_path_for_zip, 'new_disabled', 'new_disabled_accounts.txt')
    invalid_file = os.path.join(base_path_for_zip, 'invalid', '12345Noah Brooksinvalid_accounts.txt')

    files_to_zip = []
    if os.path.exists(live_file):
        files_to_zip.append(live_file)
    if os.path.exists(new_disabled_file):
        files_to_zip.append(new_disabled_file)
    if os.path.exists(invalid_file):
        files_to_zip.append(invalid_file)

    if files_to_zip:
        # Use subprocess.run for robust zip creation
        zip_output_filename = 'result_accounts.zip'
        zip_cmd = ["zip", "-j", zip_output_filename] + files_to_zip
        print(f"\nZipping files: {' '.join([shlex.quote(arg) for arg in zip_cmd])}")
        try:
            subprocess.run(zip_cmd, check=True, capture_output=True, text=True)
            print(f"\n✅ All result files have been zipped into `{zip_output_filename}`")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error zipping files: {e.stderr.strip()}")
        except Exception as e:
            print(f"❌ An unexpected error occurred during zipping: {e}")
    else:
        print("\n❌ No result files found to zip.")

    # 6. Download the zipped file
    file_to_download = '/content/result_accounts.zip'

    if os.path.exists(file_to_download):
        print(f"\nDownloading {file_to_download}...")
        files.download(file_to_download)
        print(f"✅ {file_to_download} downloaded successfully!")
    else:
        print(f"❌ Error: {file_to_download} not found for download.")

    print("\n" + "="*80)
    print("✅ Workflow Completed")
    print("="*80)

if __name__ == "__main__":
    main_workflow()