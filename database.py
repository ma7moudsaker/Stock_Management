import sqlite3
import os
from urllib.parse import urlparse
from datetime import datetime
import requests
from urllib.parse import urlparse
import re
try:
    import psycopg  # psycopg3
    from psycopg.rows import dict_row
    PSYCOPG_VERSION = 3
except ImportError:
    try:
        import psycopg2  # psycopg2
        from psycopg2.extras import RealDictCursor
        PSYCOPG_VERSION = 2
    except ImportError:
        PSYCOPG_VERSION = None


class StockDatabase:

    def __init__(self, db_name='stock_management.db'):
        if os.getenv('DATABASE_URL') and PSYCOPG_VERSION:
            self.db_type = 'postgresql'
            self.setup_postgresql()
        else:
            self.db_type = 'sqlite'
            self.db_name = db_name
        
        self.init_database()
    
    def get_connection(self):
        """الحصول على اتصال قاعدة البيانات"""
        if self.db_type == 'postgresql':
            if PSYCOPG_VERSION == 3:
                return psycopg.connect(**self.pg_config, row_factory=dict_row)
            else:
                return psycopg2.connect(**self.pg_config, cursor_factory=RealDictCursor)
        else:
            return sqlite3.connect(self.db_name, timeout=30.0)
   
   
    def setup_postgresql(self):
        """إعداد اتصال PostgreSQL"""
        database_url = os.getenv('DATABASE_URL')
        
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        parsed = urlparse(database_url)
        self.pg_config = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],
            'user': parsed.username,
            'password': parsed.password,
        }
    
    def migrate_to_postgresql(self):
        """نقل البيانات من SQLite إلى PostgreSQL"""
        if self.db_type != 'postgresql':
            print("Migration only needed for PostgreSQL")
            return
        
        # فحص إذا كانت الجداول موجودة
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM brands")
            print("✅ Database already contains data")
            conn.close()
            return
        except:
            # الجداول غير موجودة، نحتاج إنشاؤها
            conn.close()
            self.add_default_data()
            print("✅ Default data added to PostgreSQL")

    def init_database(self):
        """إنشاء الجداول - متوافق مع SQLite و PostgreSQL"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # تحديد نوع البيانات حسب قاعدة البيانات
        if self.db_type == 'postgresql':
            id_type = 'SERIAL PRIMARY KEY'
            timestamp_type = 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            decimal_type = 'DECIMAL(10,2)'
        else:
            id_type = 'INTEGER PRIMARY KEY'
            timestamp_type = 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            decimal_type = 'DECIMAL(10,2)'
        
    
        # جدول البراندات
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS brands (
                id {id_type},
                brand_name TEXT UNIQUE NOT NULL,
                created_date {timestamp_type}
            )
        ''')
        
        # جدول الألوان
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS colors (
                id {id_type},
                color_name TEXT UNIQUE NOT NULL,
                color_code TEXT,
                created_date {timestamp_type}
            )
        ''')

                
        # جدول أنواع المنتجات
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS product_types (
                id {id_type},
                type_name TEXT UNIQUE NOT NULL,
                created_date {timestamp_type}
            )
        ''')
        
        # جدول فئات التجار
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS trader_categories (
                id {id_type},
                category_code TEXT UNIQUE NOT NULL,
                category_name TEXT NOT NULL,
                description TEXT,
                created_date {timestamp_type}
            )
        ''')
        
        # جدول الموردين
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS suppliers (
                id {id_type},
                supplier_name TEXT NOT NULL,
                contact_phone TEXT,
                contact_email TEXT,
                address TEXT,
                created_date {timestamp_type}
            )
        ''')
        
        # جدول Tags
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS tags (
                id {id_type},
                tag_name TEXT UNIQUE NOT NULL,
                tag_category TEXT,
                tag_color TEXT DEFAULT '#6c757d',
                description TEXT,
                created_date {timestamp_type}
            )
        ''')
        
        # جدول المنتجات الأساسية مع المقاس
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS base_products (
                id {id_type},
                product_code TEXT NOT NULL,
                brand_id INTEGER,
                product_type_id INTEGER,
                trader_category TEXT,
                product_size TEXT,
                wholesale_price DECIMAL(10,2),
                retail_price DECIMAL(10,2),
                supplier_id INTEGER,
                created_date {timestamp_type},
                FOREIGN KEY (brand_id) REFERENCES brands(id),
                FOREIGN KEY (product_type_id) REFERENCES product_types(id),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        ''')
        
        # جدول المتغيرات (المنتجات بالألوان)
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS product_variants (
                id {id_type},
                base_product_id INTEGER,
                color_id INTEGER,
                current_stock INTEGER DEFAULT 0,
                created_date {timestamp_type},
                FOREIGN KEY (base_product_id) REFERENCES base_products(id),
                FOREIGN KEY (color_id) REFERENCES colors(id)
            )
        ''')
        
        # جدول صور الألوان المحدث
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS color_images (
                id {id_type},
                variant_id INTEGER UNIQUE NOT NULL,
                image_url TEXT,
                image_filename TEXT,
                created_date {timestamp_type},
                FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE
            )
        ''')
        
        # جدول ربط المنتجات بالـ Tags
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS product_tags (
                id {id_type},
                product_id INTEGER,
                tag_id INTEGER,
                created_date {timestamp_type},
                FOREIGN KEY (product_id) REFERENCES base_products(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(product_id, tag_id)
            )
        ''')
        
        # إضافة عمود المقاس للمنتجات الموجودة (إذا لم يكن موجود)
        try:
            cursor.execute('ALTER TABLE base_products ADD COLUMN product_size TEXT')
        except sqlite3.OperationalError:
            pass  # العمود موجود بالفعل
        
        conn.commit()
        conn.close()
        print(f"✅ Database initialized using {self.db_type}")
    
    # وظائف نظام الصور المحدث
    def create_product_folder(self, product_code):
        """إنشاء مجلد المنتج"""
        product_path = os.path.join('static', 'uploads', 'products', str(product_code))
        os.makedirs(product_path, exist_ok=True)
        return product_path
    
    def clean_color_name(self, color_name):
        """تنظيف اسم اللون للاستخدام في أسماء الملفات"""
        # تحويل لأحرف صغيرة وإزالة المسافات والأحرف الخاصة
        clean_name = color_name.lower().strip()
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', clean_name)
        clean_name = re.sub(r'_+', '_', clean_name)  # إزالة الـ underscores المتكررة
        return clean_name.strip('_')
    
    def download_and_save_image(self, image_url, product_code, color_name):
        """تحميل صورة من URL وحفظها محلياً"""
        try:
            # إنشاء مجلد المنتج
            product_folder = self.create_product_folder(product_code)
            
            # تحميل الصورة
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                # تحديد امتداد الملف
                parsed_url = urlparse(image_url)
                file_extension = os.path.splitext(parsed_url.path)[1].lower()
                if not file_extension or file_extension not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    file_extension = '.jpg'
                
                # تنظيف اسم اللون وإنشاء اسم الملف
                clean_color = self.clean_color_name(color_name)
                filename = f"{product_code}_{clean_color}{file_extension}"
                file_path = os.path.join(product_folder, filename)
                
                # حفظ الصورة
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                # إرجاع المسار النسبي
                return f"/static/uploads/products/{product_code}/{filename}"
            
            print(f"Failed to download image: HTTP {response.status_code}")
            return None
            
        except Exception as e:
            print(f"Error downloading image from {image_url}: {e}")
            return None
    
    def save_manual_image(self, uploaded_file, product_code, color_name):
        """حفظ صورة مرفوعة يدوياً"""
        try:
            from werkzeug.utils import secure_filename
            
            # إنشاء مجلد المنتج
            product_folder = self.create_product_folder(product_code)
            
            # تحديد امتداد الملف
            original_filename = secure_filename(uploaded_file.filename)
            file_extension = os.path.splitext(original_filename)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            
            # تنظيف اسم اللون وإنشاء اسم الملف
            clean_color = self.clean_color_name(color_name)
            filename = f"{product_code}_{clean_color}{file_extension}"
            file_path = os.path.join(product_folder, filename)
            
            # حفظ الصورة
            uploaded_file.save(file_path)
            
            # إرجاع المسار النسبي
            return f"/static/uploads/products/{product_code}/{filename}"
        
        except Exception as e:
            print(f"Error saving manual image: {e}")
            return None
    
    def add_default_data(self):
        """إضافة بيانات افتراضية مع Tags"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # إضافة فئات التجار
        categories = [('L', 'Category L', 'Trader Category L'), 
                     ('F', 'Category F', 'Trader Category F')]
        for cat in categories:
            cursor.execute('INSERT OR IGNORE INTO trader_categories (category_code, category_name, description) VALUES (?, ?, ?)', cat)
        
        # إضافة براندات افتراضية
        brands = ['Saint Laurent', 'Gucci', 'Louis Vuitton', 'Guess', 'Tommy Hilfiger', 'Karl Lagerfeld']
        for brand in brands:
            cursor.execute('INSERT OR IGNORE INTO brands (brand_name) VALUES (?)', (brand,))
        
        # إضافة ألوان افتراضية
        colors = [('Black', '#000000'), ('Brown', '#8B4513'), ('Red', '#FF0000'), 
                 ('White', '#FFFFFF'), ('Beige', '#F5F5DC'), ('Navy', '#000080'),
                 ('Gold', '#FFD700'), ('Silver', '#C0C0C0'), ('Pink', '#FFC0CB'), ('Blue', '#0000FF')]
        for color in colors:
            cursor.execute('INSERT OR IGNORE INTO colors (color_name, color_code) VALUES (?, ?)', color)
        
        # إضافة أنواع منتجات افتراضية
        types = ['Handbag', 'Wallet', 'Backpack', 'Clutch', 'Shoulder Bag', 'Tote Bag']
        for ptype in types:
            cursor.execute('INSERT OR IGNORE INTO product_types (type_name) VALUES (?)', (ptype,))
        
        # إضافة مورد افتراضي
        cursor.execute('INSERT OR IGNORE INTO suppliers (supplier_name, contact_phone) VALUES (?, ?)', 
                      ('Default Supplier', '01000000000'))
        
        # إضافة Tags افتراضية
        default_tags = [
            ('Small', 'size', '#28a745', 'Small size products'),
            ('Medium', 'size', '#ffc107', 'Medium size products'),
            ('Large', 'size', '#fd7e14', 'Large size products'),
            ('XL', 'size', '#dc3545', 'Extra Large size products'),
            ('Sale', 'status', '#dc3545', 'Products on sale'),
            ('New Arrival', 'status', '#28a745', 'New products'),
            ('Limited Edition', 'status', '#6f42c1', 'Limited edition products'),
            ('Valentine\'s', 'occasion', '#e83e8c', 'Valentine\'s Day collection'),
            ('Christmas', 'occasion', '#dc3545', 'Christmas collection'),
            ('Summer', 'season', '#fd7e14', 'Summer collection'),
            ('Winter', 'season', '#6c757d', 'Winter collection'),
            ('Leather', 'material', '#8B4513', 'Leather products'),
            ('Canvas', 'material', '#6c757d', 'Canvas products'),
            ('Casual', 'style', '#17a2b8', 'Casual style'),
            ('Formal', 'style', '#343a40', 'Formal style')
        ]
        
        for tag in default_tags:
            cursor.execute('INSERT OR IGNORE INTO tags (tag_name, tag_category, tag_color, description) VALUES (?, ?, ?, ?)', tag)
        
        conn.commit()
        conn.close()
        print("✅ Default data with enhanced tags added!")
    
    # وظائف إدارة البراندات
    def get_all_brands(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM brands ORDER BY brand_name')
        brands = cursor.fetchall()
        conn.close()
        return brands
    
    def add_brand(self, brand_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO brands (brand_name) VALUES (?)', (brand_name,))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def update_brand(self, brand_id, new_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE brands SET brand_name = ? WHERE id = ?', (new_name, brand_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def delete_brand(self, brand_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM base_products WHERE brand_id = ?', (brand_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False, "Cannot delete brand - it's used by existing products"
            
            cursor.execute('DELETE FROM brands WHERE id = ?', (brand_id,))
            conn.commit()
            conn.close()
            return True, "Brand deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_brand_by_id(self, brand_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM brands WHERE id = ?', (brand_id,))
        brand = cursor.fetchone()
        conn.close()
        return brand
    
    # وظائف إدارة الألوان
    def get_all_colors(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM colors ORDER BY color_name')
        colors = cursor.fetchall()
        conn.close()
        return colors
    
    def add_color(self, color_name, color_code='#FFFFFF'):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO colors (color_name, color_code) VALUES (?, ?)', (color_name, color_code))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def update_color(self, color_id, new_name, new_code):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE colors SET color_name = ?, color_code = ? WHERE id = ?', 
                          (new_name, new_code, color_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def delete_color(self, color_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM product_variants WHERE color_id = ?', (color_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False, "Cannot delete color - it's used by existing products"
            
            cursor.execute('DELETE FROM colors WHERE id = ?', (color_id,))
            conn.commit()
            conn.close()
            return True, "Color deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_color_by_id(self, color_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM colors WHERE id = ?', (color_id,))
        color = cursor.fetchone()
        conn.close()
        return color
    
    def get_color_name_by_id(self, color_id):
        """جلب اسم اللون بالـ ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT color_name FROM colors WHERE id = ?', (color_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    # وظائف إدارة أنواع المنتجات
    def get_all_product_types(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM product_types ORDER BY type_name')
        types = cursor.fetchall()
        conn.close()
        return types
    
    def add_product_type(self, type_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO product_types (type_name) VALUES (?)', (type_name,))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def update_product_type(self, type_id, new_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE product_types SET type_name = ? WHERE id = ?', (new_name, type_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def delete_product_type(self, type_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM base_products WHERE product_type_id = ?', (type_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False, "Cannot delete product type - it's used by existing products"
            
            cursor.execute('DELETE FROM product_types WHERE id = ?', (type_id,))
            conn.commit()
            conn.close()
            return True, "Product type deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_product_type_by_id(self, type_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM product_types WHERE id = ?', (type_id,))
        ptype = cursor.fetchone()
        conn.close()
        return ptype
    
    # وظائف إدارة فئات التجار
    def get_all_trader_categories(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trader_categories ORDER BY category_code')
        categories = cursor.fetchall()
        conn.close()
        return categories

    def add_trader_category(self, category_code, category_name, description=''):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO trader_categories (category_code, category_name, description) VALUES (?, ?, ?)',
                           (category_code, category_name, description))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False

    def update_trader_category(self, category_id, new_code, new_name, new_description):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE trader_categories SET category_code = ?, category_name = ?, description = ? WHERE id = ?',
                           (new_code, new_name, new_description, category_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False

    def delete_trader_category(self, category_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM base_products WHERE trader_category = (SELECT category_code FROM trader_categories WHERE id = ?)', (category_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False, "Cannot delete category - it's used by existing products"
            
            cursor.execute('DELETE FROM trader_categories WHERE id = ?', (category_id,))
            conn.commit()
            conn.close()
            return True, "Category deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)

    def get_trader_category_by_id(self, category_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trader_categories WHERE id = ?', (category_id,))
        category = cursor.fetchone()
        conn.close()
        return category

    # وظائف إدارة Tags
    def get_all_tags(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags ORDER BY tag_category, tag_name')
        tags = cursor.fetchall()
        conn.close()
        return tags
    
    def get_tags_by_category(self, category=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if category:
            cursor.execute('SELECT * FROM tags WHERE tag_category = ? ORDER BY tag_name', (category,))
        else:
            cursor.execute('SELECT DISTINCT tag_category FROM tags ORDER BY tag_category')
        tags = cursor.fetchall()
        conn.close()
        return tags
    
    def add_tag(self, tag_name, tag_category='general', tag_color='#6c757d', description=''):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO tags (tag_name, tag_category, tag_color, description) VALUES (?, ?, ?, ?)',
                           (tag_name, tag_category, tag_color, description))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def update_tag(self, tag_id, new_name, new_category, new_color, new_description):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE tags SET tag_name = ?, tag_category = ?, tag_color = ?, description = ? WHERE id = ?',
                           (new_name, new_category, new_color, new_description, tag_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def delete_tag(self, tag_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM product_tags WHERE tag_id = ?', (tag_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False, "Cannot delete tag - it's used by existing products"
            
            cursor.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            conn.commit()
            conn.close()
            return True, "Tag deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_tag_by_id(self, tag_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags WHERE id = ?', (tag_id,))
        tag = cursor.fetchone()
        conn.close()
        return tag
    
    def add_product_tags(self, product_id, tag_ids):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM product_tags WHERE product_id = ?', (product_id,))
            
            for tag_id in tag_ids:
                cursor.execute('INSERT INTO product_tags (product_id, tag_id) VALUES (?, ?)', 
                              (product_id, tag_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.close()
            return False
    
    def get_product_tags(self, product_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.* FROM tags t
            JOIN product_tags pt ON t.id = pt.tag_id
            WHERE pt.product_id = ?
            ORDER BY t.tag_category, t.tag_name
        ''', (product_id,))
        tags = cursor.fetchall()
        conn.close()
        return tags

    # وظائف إدارة المنتجات مع النظام المحدث
    def add_base_product_with_variants(self, product_code, brand_id, product_type_id, 
                                     trader_category, product_size, wholesale_price, retail_price, 
                                     color_ids, tag_ids=None, initial_stock=0, supplier_id=1):
        """إضافة منتج أساسي مع متغيرات الألوان والمقاس والـ Tags"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO base_products (product_code, brand_id, product_type_id, 
                                         trader_category, product_size, wholesale_price, retail_price, supplier_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (product_code, brand_id, product_type_id, trader_category, 
                  product_size, wholesale_price, retail_price, supplier_id))
            
            base_product_id = cursor.lastrowid
            
            for color_id in color_ids:
                cursor.execute('''
                    INSERT INTO product_variants (base_product_id, color_id, current_stock)
                    VALUES (?, ?, ?)
                ''', (base_product_id, color_id, initial_stock))
            
            if tag_ids:
                for tag_id in tag_ids:
                    cursor.execute('''
                        INSERT INTO product_tags (product_id, tag_id)
                        VALUES (?, ?)
                    ''', (base_product_id, tag_id))
            
            conn.commit()
            conn.close()
            return True, base_product_id
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def get_all_products_with_details(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                bp.id,
                bp.product_code,
                b.brand_name,
                pt.type_name,
                bp.trader_category,
                bp.product_size,
                bp.wholesale_price,
                bp.retail_price,
                s.supplier_name,
                GROUP_CONCAT(DISTINCT c.color_name) as colors,
                SUM(pv.current_stock) as total_stock,
                bp.created_date,
                GROUP_CONCAT(DISTINCT t.tag_name) as tags
            FROM base_products bp
            LEFT JOIN brands b ON bp.brand_id = b.id
            LEFT JOIN product_types pt ON bp.product_type_id = pt.id
            LEFT JOIN suppliers s ON bp.supplier_id = s.id
            LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
            LEFT JOIN colors c ON pv.color_id = c.id
            LEFT JOIN product_tags ptags ON bp.id = ptags.product_id
            LEFT JOIN tags t ON ptags.tag_id = t.id
            GROUP BY bp.id
            ORDER BY bp.created_date DESC
        ''')
        
        products = cursor.fetchall()
        conn.close()
        return products
    
    def check_product_exists(self, product_code, brand_id, trader_category):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id FROM base_products 
            WHERE product_code = ? AND brand_id = ? AND trader_category = ?
        ''', (product_code, brand_id, trader_category))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def search_products(self, search_term=''):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if search_term:
            search_term = f'%{search_term}%'
            cursor.execute('''
                SELECT DISTINCT
                    bp.id,
                    bp.product_code,
                    b.brand_name,
                    pt.type_name,
                    bp.trader_category,
                    bp.product_size,
                    bp.wholesale_price,
                    bp.retail_price,
                    s.supplier_name,
                    GROUP_CONCAT(DISTINCT c.color_name) as colors,
                    SUM(pv.current_stock) as total_stock,
                    bp.created_date,
                    GROUP_CONCAT(DISTINCT t.tag_name) as tags
                FROM base_products bp
                LEFT JOIN brands b ON bp.brand_id = b.id
                LEFT JOIN product_types pt ON bp.product_type_id = pt.id
                LEFT JOIN suppliers s ON bp.supplier_id = s.id
                LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
                LEFT JOIN colors c ON pv.color_id = c.id
                LEFT JOIN product_tags ptags ON bp.id = ptags.product_id
                LEFT JOIN tags t ON ptags.tag_id = t.id
                WHERE bp.product_code LIKE ? 
                   OR b.brand_name LIKE ?
                   OR c.color_name LIKE ?
                   OR bp.trader_category LIKE ?
                   OR pt.type_name LIKE ?
                   OR bp.product_size LIKE ?
                   OR t.tag_name LIKE ?
                GROUP BY bp.id
                ORDER BY bp.created_date DESC
            ''', (search_term, search_term, search_term, search_term, search_term, search_term, search_term))
        else:
            cursor.execute('''
                SELECT 
                    bp.id,
                    bp.product_code,
                    b.brand_name,
                    pt.type_name,
                    bp.trader_category,
                    bp.product_size,
                    bp.wholesale_price,
                    bp.retail_price,
                    s.supplier_name,
                    GROUP_CONCAT(DISTINCT c.color_name) as colors,
                    SUM(pv.current_stock) as total_stock,
                    bp.created_date,
                    GROUP_CONCAT(DISTINCT t.tag_name) as tags
                FROM base_products bp
                LEFT JOIN brands b ON bp.brand_id = b.id
                LEFT JOIN product_types pt ON bp.product_type_id = pt.id
                LEFT JOIN suppliers s ON bp.supplier_id = s.id
                LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
                LEFT JOIN colors c ON pv.color_id = c.id
                LEFT JOIN product_tags ptags ON bp.id = ptags.product_id
                LEFT JOIN tags t ON ptags.tag_id = t.id
                GROUP BY bp.id
                ORDER BY bp.created_date DESC
            ''')
        
        products = cursor.fetchall()
        conn.close()
        return products
    
    def get_product_details(self, product_id):
        """جلب تفاصيل منتج واحد مع مخزون كل لون والمقاس والـ Tags"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                bp.id, bp.product_code, bp.trader_category, bp.product_size, 
                bp.wholesale_price, bp.retail_price, bp.created_date,
                b.brand_name, pt.type_name, s.supplier_name
            FROM base_products bp
            LEFT JOIN brands b ON bp.brand_id = b.id
            LEFT JOIN product_types pt ON bp.product_type_id = pt.id
            LEFT JOIN suppliers s ON bp.supplier_id = s.id
            WHERE bp.id = ?
        ''', (product_id,))
        
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return None
        
        cursor.execute('''
            SELECT 
                pv.id as variant_id, c.id as color_id, c.color_name, c.color_code,
                pv.current_stock, ci.image_url, ci.image_filename
            FROM product_variants pv
            JOIN colors c ON pv.color_id = c.id
            LEFT JOIN color_images ci ON pv.id = ci.variant_id
            WHERE pv.base_product_id = ?
            ORDER BY pv.current_stock DESC, c.color_name
        ''', (product_id,))
        
        color_stocks = cursor.fetchall()
        
        product_tags = self.get_product_tags(product_id)
        
        total_stock = sum([stock[4] for stock in color_stocks])
        
        conn.close()
        
        return {
            'product': product,
            'color_stocks': color_stocks,
            'total_stock': total_stock,
            'tags': product_tags
        }
    
    def delete_product(self, product_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM product_tags WHERE product_id = ?', (product_id,))
            cursor.execute('DELETE FROM product_variants WHERE base_product_id = ?', (product_id,))
            cursor.execute('DELETE FROM base_products WHERE id = ?', (product_id,))
            
            conn.commit()
            conn.close()
            return True, "Product deleted successfully"
        except Exception as e:
            conn.close()
            return False, str(e)
    
    # وظائف إدارة الصور المحدثة
    def add_color_image(self, variant_id, image_url, image_filename=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO color_images (variant_id, image_url, image_filename)
                VALUES (?, ?, ?)
            ''', (variant_id, image_url, image_filename))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding color image: {e}")
            conn.close()
            return False
    
    def get_product_images_with_details(self, product_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                bp.id, bp.product_code, bp.trader_category, bp.product_size, 
                bp.wholesale_price, bp.retail_price, bp.created_date,
                b.brand_name, pt.type_name, s.supplier_name,
                pv.id as variant_id, c.id as color_id, c.color_name, c.color_code,
                pv.current_stock, ci.image_url, ci.image_filename
            FROM base_products bp
            LEFT JOIN brands b ON bp.brand_id = b.id
            LEFT JOIN product_types pt ON bp.product_type_id = pt.id
            LEFT JOIN suppliers s ON bp.supplier_id = s.id
            LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
            LEFT JOIN colors c ON pv.color_id = c.id
            LEFT JOIN color_images ci ON pv.id = ci.variant_id
            WHERE bp.id = ?
            ORDER BY pv.current_stock DESC, c.color_name
        ''', (product_id,))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_product_main_image(self, product_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ci.image_url
            FROM product_variants pv
            LEFT JOIN color_images ci ON pv.id = ci.variant_id
            WHERE pv.base_product_id = ? AND ci.image_url IS NOT NULL
            ORDER BY pv.current_stock DESC, pv.id ASC
            LIMIT 1
        ''', (product_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_products_with_color_images(self, search_term=''):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if search_term:
            search_term = f'%{search_term}%'
            cursor.execute('''
                SELECT DISTINCT
                    bp.id, bp.product_code, b.brand_name, pt.type_name,
                    bp.trader_category, bp.product_size, bp.wholesale_price, bp.retail_price,
                    s.supplier_name, bp.created_date
                FROM base_products bp
                LEFT JOIN brands b ON bp.brand_id = b.id
                LEFT JOIN product_types pt ON bp.product_type_id = pt.id
                LEFT JOIN suppliers s ON bp.supplier_id = s.id
                LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
                LEFT JOIN colors c ON pv.color_id = c.id
                LEFT JOIN product_tags ptags ON bp.id = ptags.product_id
                LEFT JOIN tags t ON ptags.tag_id = t.id
                WHERE bp.product_code LIKE ? OR b.brand_name LIKE ? OR c.color_name LIKE ? 
                   OR bp.product_size LIKE ? OR t.tag_name LIKE ?
                ORDER BY bp.created_date DESC
            ''', (search_term, search_term, search_term, search_term, search_term))
        else:
            cursor.execute('''
                SELECT 
                    bp.id, bp.product_code, b.brand_name, pt.type_name,
                    bp.trader_category, bp.product_size, bp.wholesale_price, bp.retail_price,
                    s.supplier_name, bp.created_date
                FROM base_products bp
                LEFT JOIN brands b ON bp.brand_id = b.id
                LEFT JOIN product_types pt ON bp.product_type_id = pt.id
                LEFT JOIN suppliers s ON bp.supplier_id = s.id
                ORDER BY bp.created_date DESC
            ''')
        
        products = cursor.fetchall()
        
        products_with_images = []
        for product in products:
            cursor.execute('''
                SELECT 
                    pv.id as variant_id,
                    c.color_name,
                    c.color_code,
                    pv.current_stock,
                    ci.image_url
                FROM product_variants pv
                JOIN colors c ON pv.color_id = c.id
                LEFT JOIN color_images ci ON pv.id = ci.variant_id
                WHERE pv.base_product_id = ?
                ORDER BY pv.current_stock DESC
            ''', (product[0],))
            
            color_data = cursor.fetchall()
            total_stock = sum([cd[3] for cd in color_data])
            
            product_tags = self.get_product_tags(product[0])
            
            colors_with_images = []
            for cd in color_data:
                colors_with_images.append({
                    'variant_id': cd[0],
                    'name': cd[1],
                    'code': cd[2],
                    'stock': cd[3],
                    'image_url': cd[4]
                })
            
            product_data = list(product) + [colors_with_images, total_stock, product_tags]
            products_with_images.append(product_data)
        
        conn.close()
        return products_with_images

    # وظائف إضافة منتجات متعددة دفعة واحدة
    def add_multiple_products_batch(self, products_data):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        success_count = 0
        failed_products = []
        
        try:
            for product_data in products_data:
                try:
                    if self.check_product_exists(
                        product_data['product_code'], 
                        product_data['brand_id'], 
                        product_data['trader_category']
                    ):
                        failed_products.append({
                            'product': product_data,
                            'error': 'Product already exists'
                        })
                        continue
                    
                    cursor.execute('''
                        INSERT INTO base_products (product_code, brand_id, product_type_id, 
                                                 trader_category, product_size, wholesale_price, retail_price, supplier_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        product_data['product_code'],
                        product_data['brand_id'],
                        product_data['product_type_id'],
                        product_data['trader_category'],
                        product_data.get('product_size', ''),
                        product_data['wholesale_price'],
                        product_data['retail_price'],
                        product_data.get('supplier_id', 1)
                    ))
                    
                    base_product_id = cursor.lastrowid
                    
                    for color_id in product_data['color_ids']:
                        cursor.execute('''
                            INSERT INTO product_variants (base_product_id, color_id, current_stock)
                            VALUES (?, ?, ?)
                        ''', (base_product_id, color_id, product_data.get('initial_stock', 0)))
                    
                    if 'tag_ids' in product_data and product_data['tag_ids']:
                        for tag_id in product_data['tag_ids']:
                            cursor.execute('''
                                INSERT INTO product_tags (product_id, tag_id)
                                VALUES (?, ?)
                            ''', (base_product_id, tag_id))
                    
                    success_count += 1
                    
                except Exception as e:
                    failed_products.append({
                        'product': product_data,
                        'error': str(e)
                    })
                    continue
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'success_count': success_count,
                'failed_count': len(failed_products),
                'failed_products': failed_products
            }
            
        except Exception as e:
            conn.rollback()
            conn.close()
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'failed_count': len(products_data)
            }


    def get_all_products_for_inventory(self, search_term='', brand_filter='', category_filter=''):
        """جلب جميع المنتجات للجرد الشامل مع تفاصيل كل لون والصور"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        base_query = '''
            SELECT 
                bp.id, bp.product_code, b.brand_name, pt.type_name,
                bp.trader_category, bp.product_size, bp.wholesale_price, 
                bp.retail_price, bp.created_date
            FROM base_products bp
            LEFT JOIN brands b ON bp.brand_id = b.id
            LEFT JOIN product_types pt ON bp.product_type_id = pt.id
            WHERE 1=1
        '''
        
        params = []
        
        if search_term:
            base_query += ' AND (bp.product_code LIKE ? OR b.brand_name LIKE ? OR bp.product_size LIKE ?)'
            search_param = f'%{search_term}%'
            params.extend([search_param, search_param, search_param])
        
        if brand_filter:
            base_query += ' AND b.brand_name = ?'
            params.append(brand_filter)
        
        if category_filter:
            base_query += ' AND bp.trader_category = ?'
            params.append(category_filter)
        
        base_query += ' ORDER BY b.brand_name, bp.product_code'
        
        cursor.execute(base_query, params)
        products = cursor.fetchall()
        
        inventory_data = []
        for product in products:
            cursor.execute('''
                SELECT pv.id, c.id, c.color_name, c.color_code, pv.current_stock, ci.image_url
                FROM product_variants pv
                JOIN colors c ON pv.color_id = c.id
                LEFT JOIN color_images ci ON pv.id = ci.variant_id
                WHERE pv.base_product_id = ?
                ORDER BY c.color_name
            ''', (product[0],))
            
            color_variants = cursor.fetchall()
            total_stock = sum([cv[4] for cv in color_variants])
            product_tags = self.get_product_tags(product[0])
            
            inventory_data.append({
                'product': product,
                'color_variants': color_variants,
                'total_stock': total_stock,
                'tags': product_tags
            })
        
        conn.close()
        return inventory_data

    def get_inventory_summary(self):
        """جلب ملخص المخزون للتقارير"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT bp.id) as total_products,
                COUNT(pv.id) as total_variants,
                SUM(pv.current_stock) as total_stock,
                SUM(CASE WHEN pv.current_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_variants,
                SUM(CASE WHEN pv.current_stock > 0 AND pv.current_stock <= 5 THEN 1 ELSE 0 END) as low_stock_variants
            FROM base_products bp
            LEFT JOIN product_variants pv ON bp.id = pv.base_product_id
        ''')
        
        summary = cursor.fetchone()
        conn.close()
        
        return {
            'total_products': summary[0] or 0,
            'total_variants': summary[1] or 0,
            'total_stock': summary[2] or 0,
            'out_of_stock_variants': summary[3] or 0,
            'low_stock_variants': summary[4] or 0
        }

    def get_brands_for_filter(self):
        """جلب البراندات للفلترة"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT brand_name FROM brands ORDER BY brand_name')
        brands = [row[0] for row in cursor.fetchall()]
        conn.close()
        return brands

    def get_categories_for_filter(self):
        """جلب فئات التجار للفلترة"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT category_code FROM trader_categories ORDER BY category_code')
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories

    def bulk_update_inventory(self, stock_updates):
        """تحديث المخزون بشكل جماعي"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        success_count = 0
        failed_updates = []
        
        try:
            for update in stock_updates:
                try:
                    cursor.execute('''
                        UPDATE product_variants 
                        SET current_stock = ? 
                        WHERE id = ?
                    ''', (update['new_stock'], update['variant_id']))
                    
                    success_count += 1
                    
                except Exception as e:
                    failed_updates.append({
                        'variant_id': update['variant_id'],
                        'error': str(e)
                    })
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'updated_count': success_count,
                'failed_count': len(failed_updates),
                'failed_updates': failed_updates
            }
            
        except Exception as e:
            conn.rollback()
            conn.close()
            return {
                'success': False,
                'error': str(e)
            }


    def bulk_add_products_from_excel_enhanced(self, excel_data):
        """إضافة منتجات من Excel مع النظام المحسن - كل لون في صف منفصل"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        success_count = 0
        failed_products = []
        processed_products = {}  # لتجنب تكرار المنتجات
        created_brands = []
        created_colors = []
        created_types = []
        
        try:
            for index, row in enumerate(excel_data, 1):
                try:
                    # استخراج البيانات الأساسية
                    product_code = str(row['Product Code']).strip()
                    brand_name = str(row['Brand Name']).strip()
                    product_type_name = str(row['Product Type']).strip()
                    color_name = str(row['Color Name']).strip()
                    
                    if not product_code or not brand_name or not color_name:
                        failed_products.append({
                            'row': index,
                            'product_code': product_code,
                            'error': 'Missing required data (Product Code, Brand Name, or Color Name)'
                        })
                        continue
                    
                    # البحث عن أو إنشاء Brand
                    cursor.execute('SELECT id FROM brands WHERE brand_name = ?', (brand_name,))
                    brand_result = cursor.fetchone()
                    if not brand_result:
                        cursor.execute('INSERT INTO brands (brand_name) VALUES (?)', (brand_name,))
                        brand_id = cursor.lastrowid
                        created_brands.append(brand_name)
                        print(f"✅ تم إنشاء براند جديد: {brand_name}")
                    else:
                        brand_id = brand_result[0]
                    
                    # البحث عن أو إنشاء Product Type
                    cursor.execute('SELECT id FROM product_types WHERE type_name = ?', (product_type_name,))
                    type_result = cursor.fetchone()
                    if not type_result:
                        cursor.execute('INSERT INTO product_types (type_name) VALUES (?)', (product_type_name,))
                        product_type_id = cursor.lastrowid
                        created_types.append(product_type_name)
                        print(f"✅ تم إنشاء نوع منتج جديد: {product_type_name}")
                    else:
                        product_type_id = type_result[0]
                    
                    # البحث عن أو إنشاء Color
                    cursor.execute('SELECT id FROM colors WHERE color_name = ?', (color_name,))
                    color_result = cursor.fetchone()
                    if not color_result:
                        # إنشاء لون جديد مع كود افتراضي
                        default_color_codes = {
                            'black': '#000000', 'white': '#FFFFFF', 'red': '#FF0000',
                            'blue': '#0000FF', 'green': '#008000', 'yellow': '#FFFF00',
                            'brown': '#8B4513', 'pink': '#FFC0CB', 'purple': '#800080',
                            'orange': '#FFA500', 'gray': '#808080', 'grey': '#808080',
                            'gold': '#FFD700', 'silver': '#C0C0C0', 'navy': '#000080',
                            'beige': '#F5F5DC', 'maroon': '#800000'
                        }
                        color_code = default_color_codes.get(color_name.lower(), '#FFFFFF')
                        
                        cursor.execute('INSERT INTO colors (color_name, color_code) VALUES (?, ?)', 
                                     (color_name, color_code))
                        color_id = cursor.lastrowid
                        created_colors.append(color_name)
                        print(f"✅ تم إنشاء لون جديد: {color_name} ({color_code})")
                    else:
                        color_id = color_result[0]
                    
                    # إنشاء أو تحديث المنتج الأساسي
                    product_key = f"{product_code}_{brand_id}"
                    if product_key not in processed_products:
                        # التحقق من وجود المنتج
                        cursor.execute('''
                            SELECT id FROM base_products 
                            WHERE product_code = ? AND brand_id = ? AND trader_category = ?
                        ''', (product_code, brand_id, row['Category']))
                        
                        existing_product = cursor.fetchone()
                        
                        if existing_product:
                            base_product_id = existing_product[0]
                            # تحديث بيانات المنتج الموجود
                            cursor.execute('''
                                UPDATE base_products 
                                SET product_type_id = ?, product_size = ?, 
                                    wholesale_price = ?, retail_price = ?
                                WHERE id = ?
                            ''', (product_type_id, row.get('Size', ''), 
                                  float(row['Wholesale Price']), float(row['Retail Price']), 
                                  base_product_id))
                        else:
                            # إنشاء منتج جديد
                            cursor.execute('''
                                INSERT INTO base_products 
                                (product_code, brand_id, product_type_id, trader_category, 
                                 product_size, wholesale_price, retail_price, supplier_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (product_code, brand_id, product_type_id, row['Category'],
                                  row.get('Size', ''), float(row['Wholesale Price']), 
                                  float(row['Retail Price']), 1))
                            base_product_id = cursor.lastrowid
                        
                        processed_products[product_key] = base_product_id
                    else:
                        base_product_id = processed_products[product_key]
                    
                    # إضافة أو تحديث متغير اللون
                    stock = int(row.get('Stock', 0))
                    cursor.execute('''
                        SELECT id FROM product_variants 
                        WHERE base_product_id = ? AND color_id = ?
                    ''', (base_product_id, color_id))
                    
                    existing_variant = cursor.fetchone()
                    
                    if existing_variant:
                        # تحديث المخزون الموجود
                        variant_id = existing_variant[0]
                        cursor.execute('''
                            UPDATE product_variants 
                            SET current_stock = ?
                            WHERE id = ?
                        ''', (stock, variant_id))
                    else:
                        # إنشاء متغير جديد
                        cursor.execute('''
                            INSERT INTO product_variants 
                            (base_product_id, color_id, current_stock)
                            VALUES (?, ?, ?)
                        ''', (base_product_id, color_id, stock))
                        variant_id = cursor.lastrowid
                    
                    # إضافة أو تحديث الصورة
                    image_url = row.get('Image URL', '').strip()
                    if image_url:
                        try:
                            local_image_path = self.download_and_save_image(image_url, product_code, color_name)
                            if local_image_path:
                                filename = os.path.basename(local_image_path)
                                cursor.execute('''
                                    INSERT OR REPLACE INTO color_images 
                                    (variant_id, image_url, image_filename)
                                    VALUES (?, ?, ?)
                                ''', (variant_id, local_image_path, filename))
                                print(f"✅ تم تحميل صورة: {product_code} - {color_name}")
                        except Exception as img_error:
                            print(f"⚠️ فشل تحميل صورة {product_code} - {color_name}: {img_error}")
                    
                    # إضافة Tags (فقط للمنتج الأساسي مرة واحدة)
                    tags = row.get('Tags', '').strip()
                    if tags and product_key not in [p for p in processed_products.keys() if p.startswith(product_code)][:-1]:
                        tag_names = [tag.strip() for tag in tags.split(',') if tag.strip()]
                        for tag_name in tag_names:
                            cursor.execute('SELECT id FROM tags WHERE tag_name = ?', (tag_name,))
                            tag_result = cursor.fetchone()
                            if tag_result:
                                cursor.execute('''
                                    INSERT OR IGNORE INTO product_tags (product_id, tag_id)
                                    VALUES (?, ?)
                                ''', (base_product_id, tag_result[0]))
                    
                    success_count += 1
                    
                except Exception as e:
                    failed_products.append({
                        'row': index,
                        'product_code': row.get('Product Code', 'Unknown'),
                        'color': row.get('Color Name', 'Unknown'),
                        'error': str(e)
                    })
                    print(f"❌ خطأ في الصف {index}: {str(e)}")
                    continue
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'success_count': success_count,
                'failed_count': len(failed_products),
                'failed_products': failed_products,
                'unique_products': len(set([k.split('_')[0] for k in processed_products.keys()])),
                'created_brands': list(set(created_brands)),
                'created_colors': list(set(created_colors)),
                'created_types': list(set(created_types))
            }
            
        except Exception as e:
            conn.rollback()
            conn.close()
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'failed_count': len(excel_data)
            }
# اختبار قاعدة البيانات المحدثة
if __name__ == "__main__":
    db = StockDatabase()
    db.add_default_data()
    print("✅ Enhanced database structure with organized image system ready!")
    print("📦 Features: Products, Colors, Brands, Types, Categories, Tags, Organized Images, Size")
