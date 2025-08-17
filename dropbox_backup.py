import dropbox
import json
import sqlite3
from datetime import datetime
import os

class DropboxBackup:
    def __init__(self):
        self.access_token = os.getenv('DROPBOX_ACCESS_TOKEN')
        self.dbx = dropbox.Dropbox(self.access_token) if self.access_token else None
        self.max_backups = 10  # احتفظ بـ 10 نسخ فقط
        
        if not self.access_token:
            print("⚠️ DROPBOX_ACCESS_TOKEN غير موجود")
        else:
            print("✅ Dropbox متصل بنجاح")
    
    def export_database_to_json(self):
        """تصدير قاعدة البيانات لـ JSON"""
        try:
            conn = sqlite3.connect('stock_management.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            backup_data = {
                'backup_date': datetime.now().isoformat(),
                'version': '2.0',
                'source': 'dropbox_backup',
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
            
            total_records = 0
            for table_name in important_tables:
                try:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchall()
                    backup_data['tables'][table_name] = [dict(row) for row in rows]
                    print(f"✅ تم تصدير {len(rows)} سجل من جدول {table_name}")
                    total_records += len(rows)
                except Exception as e:
                    print(f"⚠️ تخطي جدول {table_name}: {e}")
            
            conn.close()
            print(f"📊 إجمالي السجلات المُصدرة: {total_records}")
            return backup_data
            
        except Exception as e:
            print(f"❌ خطأ في تصدير قاعدة البيانات: {e}")
            return None
    
    def create_backup(self):
        """إنشاء نسخة احتياطية في Dropbox"""
        print("🔄 بدء إنشاء نسخة احتياطية في Dropbox...")
        
        if not self.dbx:
            print("❌ Dropbox غير متصل - حفظ محلياً")
            return self.create_local_backup()
        
        try:
            # تصدير البيانات
            backup_data = self.export_database_to_json()
            if not backup_data:
                return False
            
            # إنشاء اسم الملف
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'stock_backup_{timestamp}.json'
            
            # تحويل لـ JSON string
            json_content = json.dumps(backup_data, ensure_ascii=False, indent=2)
            content_size = len(json_content.encode('utf-8'))
            
            print(f"📦 حجم النسخة الاحتياطية: {content_size / 1024:.1f} KB")
            
            # رفع لـ Dropbox
            self.dbx.files_upload(
                json_content.encode('utf-8'),
                f'/{filename}',
                mode=dropbox.files.WriteMode.overwrite
            )
            
            print(f"✅ تم رفع النسخة الاحتياطية بنجاح: {filename}")
            
            # تنظيف النسخ القديمة
            self.cleanup_old_backups()
            
            return True
            
        except dropbox.exceptions.AuthError as e:
            print(f"❌ خطأ في المصادقة: {e}")
            return self.create_local_backup()
        except dropbox.exceptions.ApiError as e:
            print(f"❌ خطأ في Dropbox API: {e}")
            return self.create_local_backup()
        except Exception as e:
            print(f"❌ خطأ عام: {e}")
            return self.create_local_backup()
    
    def list_backups(self):
        """قائمة النسخ الاحتياطية في Dropbox"""
        if not self.dbx:
            return []
        
        try:
            result = self.dbx.files_list_folder('')
            backups = []
            
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata) and entry.name.startswith('stock_backup_'):
                    backups.append({
                        'name': entry.name,
                        'size': entry.size,
                        'modified': entry.server_modified.isoformat() if entry.server_modified else 'غير محدد',
                        'path': entry.path_display
                    })
            
            # ترتيب حسب التاريخ (الأحدث أولاً)
            backups.sort(key=lambda x: x['name'], reverse=True)
            return backups
            
        except Exception as e:
            print(f"❌ خطأ في جلب قائمة النسخ: {e}")
            return []
    
    def cleanup_old_backups(self):
        """حذف النسخ القديمة الزائدة"""
        try:
            backups = self.list_backups()
            
            if len(backups) > self.max_backups:
                # حذف النسخ الزائدة (الأقدم)
                old_backups = backups[self.max_backups:]
                
                for backup in old_backups:
                    self.dbx.files_delete_v2(backup['path'])
                    print(f"🗑️ حذف نسخة قديمة: {backup['name']}")
                    
        except Exception as e:
            print(f"⚠️ خطأ في تنظيف النسخ القديمة: {e}")
    
    def restore_from_backup(self, backup_name=None):
        """استرجاع من نسخة احتياطية"""
        if not self.dbx:
            print("❌ Dropbox غير متصل")
            return False
        
        try:
            # إذا لم يُحدد اسم النسخة، استخدم الأحدث
            if not backup_name:
                backups = self.list_backups()
                if not backups:
                    print("❌ لا توجد نسخ احتياطية")
                    return False
                backup_name = backups[0]['name']
            
            print(f"🔄 استرجاع من النسخة: {backup_name}")
            
            # تحميل النسخة الاحتياطية
            metadata, response = self.dbx.files_download(f'/{backup_name}')
            backup_content = response.content.decode('utf-8')
            backup_data = json.loads(backup_content)
            
            # استرجاع البيانات
            success = self.restore_data_to_database(backup_data)
            
            if success:
                print(f"✅ تم استرجاع البيانات بنجاح من: {backup_name}")
            else:
                print(f"❌ فشل في استرجاع البيانات")
            
            return success
            
        except Exception as e:
            print(f"❌ خطأ في الاسترجاع: {e}")
            return False
    
    def restore_data_to_database(self, backup_data):
        """استرجاع البيانات لقاعدة البيانات"""
        try:
            conn = sqlite3.connect('stock_management.db')
            cursor = conn.cursor()
            
            # مسح البيانات الحالية (اختياري - احذف إذا تريد إضافة فقط)
            for table_name in backup_data['tables'].keys():
                try:
                    cursor.execute(f"DELETE FROM {table_name}")
                    print(f"🗑️ تم مسح جدول {table_name}")
                except:
                    pass
            
            # استرجاع البيانات
            total_restored = 0
            for table_name, rows in backup_data['tables'].items():
                if not rows:
                    continue
                
                try:
                    # بناء استعلام الإدراج
                    columns = list(rows[0].keys())
                    placeholders = ', '.join(['?' for _ in columns])
                    insert_sql = f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                    
                    # إدراج البيانات
                    for row in rows:
                        values = [row[col] for col in columns]
                        cursor.execute(insert_sql, values)
                    
                    print(f"✅ تم استرجاع {len(rows)} سجل لجدول {table_name}")
                    total_restored += len(rows)
                    
                except Exception as e:
                    print(f"⚠️ خطأ في استرجاع جدول {table_name}: {e}")
            
            conn.commit()
            conn.close()
            
            print(f"🎉 تم استرجاع {total_restored} سجل بنجاح!")
            return True
            
        except Exception as e:
            print(f"❌ خطأ في استرجاع البيانات: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            return False
    
    def create_local_backup(self):
        """نسخة احتياطية محلية كـ fallback"""
        try:
            backup_data = self.export_database_to_json()
            if not backup_data:
                return False
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'local_backup_{timestamp}.json'
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ نسخة احتياطية محلية: {filename}")
            return True
            
        except Exception as e:
            print(f"❌ فشل النسخ الاحتياطي المحلي: {e}")
            return False
