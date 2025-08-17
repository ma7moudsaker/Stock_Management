import json
import sqlite3
from datetime import datetime
import os
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

class GoogleDriveBackup:
    def __init__(self):
        self.drive_service = None
        self.backup_folder_id = None
        self.setup_drive_service()
    
    def setup_drive_service(self):
        """إعداد خدمة Google Drive"""
        try:
            # جلب credentials
            credentials = self.get_credentials()
            if not credentials:
                print("❌ لم يتم العثور على credentials")
                return False
            
            # إنشاء service object
            self.drive_service = build('drive', 'v3', credentials=credentials)
            print("✅ تم الاتصال بـ Google Drive بنجاح")
            
            # إنشاء أو العثور على مجلد النسخ الاحتياطية
            self.setup_backup_folder()
            return True
            
        except Exception as e:
            print(f"❌ خطأ في إعداد Google Drive: {e}")
            return False
    
    def get_credentials(self):
        """جلب credentials من متغير البيئة أو ملف"""
        try:
            # من متغير البيئة (للإنتاج على Render)
            creds_base64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
            if creds_base64:
                creds_json = base64.b64decode(creds_base64).decode('utf-8')
                creds_data = json.loads(creds_json)
                
                credentials = service_account.Credentials.from_service_account_info(
                    creds_data,
                    scopes=['https://www.googleapis.com/auth/drive.file']
                )
                return credentials
            
            # من ملف محلي (للتطوير)
            if os.path.exists('google-credentials.json'):
                credentials = service_account.Credentials.from_service_account_file(
                    'google-credentials.json',
                    scopes=['https://www.googleapis.com/auth/drive.file']
                )
                return credentials
            
            print("⚠️ لم يتم العثور على Google credentials")
            return None
            
        except Exception as e:
            print(f"❌ خطأ في جلب credentials: {e}")
            return None
    
    def setup_backup_folder(self):
        """إنشاء أو العثور على مجلد النسخ الاحتياطية"""
        try:
            if not self.drive_service:
                print("⚠️ Drive service غير متاح")
                return
            
            # البحث عن المجلد الموجود
            query = "name='Stock_Management_Backups' and mimeType='application/vnd.google-apps.folder'"
            results = self.drive_service.files().list(q=query).execute()
            folders = results.get('files', [])
            
            print(f"🔍 تم العثور على {len(folders)} مجلد")
            
            if folders and len(folders) > 0:
                first_folder = folders
                if isinstance(first_folder, dict) and 'id' in first_folder:
                    self.backup_folder_id = first_folder['id']
                    print(f"✅ تم العثور على مجلد النسخ الاحتياطية: {self.backup_folder_id}")
                else:
                    print(f"⚠️ تنسيق مجلد غير متوقع: {type(first_folder)}")
                    raise Exception("تنسيق نتيجة البحث غير متوقع")
            else:
                # إنشاء مجلد جديد
                print("📁 إنشاء مجلد جديد...")
                folder_metadata = {
                    'name': 'Stock_Management_Backups',
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.drive_service.files().create(body=folder_metadata).execute()
                
                if isinstance(folder, dict) and 'id' in folder:
                    self.backup_folder_id = folder['id']
                    print(f"✅ تم إنشاء مجلد النسخ الاحتياطية: {self.backup_folder_id}")
                else:
                    raise Exception("فشل في إنشاء المجلد")
                    
        except Exception as e:
            print(f"❌ خطأ في إعداد مجلد النسخ الاحتياطية: {e}")
            self.backup_folder_id = None
        
    def export_database_to_json(self):
        """تصدير قاعدة البيانات لـ JSON"""
        try:
            conn = sqlite3.connect('stock_management.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            backup_data = {
                'backup_date': datetime.now().isoformat(),
                'version': '1.0',
                'app_info': {
                    'name': 'Stock Management System',
                    'backup_type': 'full_database'
                },
                'tables': {}
            }
            
            # قائمة الجداول المهمة
            important_tables = [
                'brands', 'colors', 'product_types', 'trader_categories',
                'suppliers', 'tags', 'base_products', 'product_variants',
                'color_images', 'product_tags'
            ]
            
            for table_name in important_tables:
                try:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchall()
                    backup_data['tables'][table_name] = [dict(row) for row in rows]
                    print(f"✅ تم تصدير {len(rows)} سجل من جدول {table_name}")
                except Exception as e:
                    print(f"⚠️ تخطي جدول {table_name}: {e}")
            
            conn.close()
            return backup_data
            
        except Exception as e:
            print(f"❌ خطأ في تصدير قاعدة البيانات: {e}")
            return None
    
    def upload_to_drive(self, backup_data):
        """رفع النسخة الاحتياطية لـ Google Drive"""
        try:
            if not self.drive_service or not self.backup_folder_id:
                print("❌ Google Drive غير مُعد بشكل صحيح")
                return False
            
            # إنشاء اسم الملف
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'stock_backup_{timestamp}.json'
            
            # تحويل البيانات إلى JSON
            json_content = json.dumps(backup_data, ensure_ascii=False, indent=2)
            
            # حفظ مؤقت
            temp_file = f'/tmp/{filename}'
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(json_content)
            
            # رفع إلى Drive
            file_metadata = {
                'name': filename,
                'parents': [self.backup_folder_id]
            }
            
            media = MediaFileUpload(temp_file, mimetype='application/json')
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # حذف الملف المؤقت
            os.remove(temp_file)
            
            print(f"✅ تم رفع النسخة الاحتياطية: {filename}")
            return file.get('id')
            
        except Exception as e:
            print(f"❌ خطأ في رفع النسخة الاحتياطية: {e}")
            return False
    
    def create_backup(self):
        """إنشاء نسخة احتياطية كاملة"""
        try:
            print("🔄 بدء إنشاء نسخة احتياطية...")
            
            # تصدير البيانات
            backup_data = self.export_database_to_json()
            if not backup_data:
                return False
            
            # رفع إلى Google Drive
            file_id = self.upload_to_drive(backup_data)
            if file_id:
                print("🎉 تم إنشاء النسخة الاحتياطية بنجاح!")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ خطأ في إنشاء النسخة الاحتياطية: {e}")
            return False
    
    def list_backups(self):
        """قائمة بجميع النسخ الاحتياطية"""
        try:
            if not self.drive_service or not self.backup_folder_id:
                return []
            
            query = f"parents='{self.backup_folder_id}' and name contains 'stock_backup_'"
            results = self.drive_service.files().list(
                q=query,
                orderBy='createdTime desc',
                fields="files(id, name, createdTime, size)"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            print(f"❌ خطأ في جلب قائمة النسخ الاحتياطية: {e}")
            return []
