import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
from database import StockDatabase
import pandas as pd
from io import BytesIO
from dropbox_backup import DropboxBackup
app = Flask(__name__)

# إعدادات الأمان والإنتاج
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-for-dev')

# إعداد رفع الصور
UPLOAD_FOLDER = 'static/uploads/products'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# إنشاء قاعدة البيانات
print("🔄 Initializing database...")
db = StockDatabase()
print("✅ Database initialized!")

# إضافة البيانات الافتراضية فقط في البيئة المحلية
if not os.getenv('DATABASE_URL'):
    db.add_default_data()
    print("✅ Default data added!")

import atexit
import threading
import time

# إنشاء نظام النسخ الاحتياطية
backup_system = DropboxBackup()

# متغير للتأكد من تشغيل الكود مرة واحدة فقط
startup_completed = False
@app.before_request
def restore_on_startup():
    """استرجاع البيانات عند بدء التطبيق"""
    global startup_completed
    
    if not startup_completed:
        try:
            print("🔄 فحص الحاجة للاستعادة...")
            
            # فحص إذا كانت قاعدة البيانات فارغة
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM base_products")
            brand_count = cursor.fetchone()[0]
            conn.close()
            
            if brand_count == 0:
                print("🔄 قاعدة البيانات فارغة - محاولة استرجاع من Dropbox...")
                success = backup_system.restore_from_backup()
                if not success:
                    print("⚠️ فشل الاستعادة - إضافة البيانات الافتراضية...")
                    db.add_default_data()
            else:
                print(f"✅ قاعدة البيانات تحتوي على {brand_count} براند")
                
        except Exception as e:
            print(f"خطأ في عملية البدء: {e}")
            db.add_default_data()
        
        startup_completed = True
        print("✅ تم الانتهاء من عملية البدء")

def auto_backup():
    """نسخ احتياطية تلقائية كل ساعة"""
    while True:
        time.sleep(3600)  # كل ساعة
        print("🔄 إنشاء نسخة احتياطية تلقائية...")
        backup_system.create_backup()

# بدء النسخ الاحتياطية التلقائية
backup_thread = threading.Thread(target=auto_backup)
backup_thread.daemon = True
backup_thread.start()
print("✅ تم بدء نظام النسخ الاحتياطية التلقائية (Dropbox)")

# نسخة احتياطية عند إغلاق التطبيق
@atexit.register
def backup_on_exit():
    print("🔄 إنشاء نسخة احتياطية قبل الإغلاق...")
    # إضافة تأخير للتأكد من اكتمال العمليات
    import time
    time.sleep(3)
    backup_system.create_backup()

# routes الجديدة للنسخ الاحتياطية
@app.route('/admin/backup')
def backup_page():
    """صفحة إدارة النسخ الاحتياطية"""
    backups = backup_system.list_backups()
    return render_template('backup_system.html', backups=backups, service="Dropbox")

@app.route('/admin/backup/create')
def create_backup():
    """إنشاء نسخة احتياطية فورية"""
    success = backup_system.create_backup()
    if success:
        flash('تم إنشاء النسخة الاحتياطية في Dropbox بنجاح!', 'success')
    else:
        flash('خطأ في إنشاء النسخة الاحتياطية', 'error')
    
    return redirect(url_for('backup_page'))

@app.route('/admin/backup/status')
def backup_status():
    """حالة نظام النسخ الاحتياطية"""
    backups = backup_system.list_backups()
    status = {
        'service': 'Dropbox',
        'connected': backup_system.dbx is not None,
        'backup_count': len(backups),
        'latest_backup': backups[0]['name'] if backups else 'لا توجد نسخ'
    }
    return jsonify(status)

@app.route('/admin/backup/restore/<backup_name>')
def restore_backup(backup_name):
    """استرجاع نسخة احتياطية محددة"""
    success = backup_system.restore_from_backup(backup_name)
    if success:
        flash(f'تم استرجاع البيانات من {backup_name} بنجاح!', 'success')
    else:
        flash('فشل في استرجاع البيانات', 'error')
    
    return redirect(url_for('backup_page'))

@app.route('/')
def dashboard():
    """الصفحة الرئيسية - Dashboard"""
    brands = db.get_all_brands()
    colors = db.get_all_colors()
    product_types = db.get_all_product_types()
    trader_categories = db.get_all_trader_categories()
    tags = db.get_all_tags()
    products = db.get_all_products_with_details()
    
    stats = {
        'total_products': len(products),
        'total_stock_value': sum([float(p[6] or 0) * int(p[10] or 0) for p in products]),
        'low_stock_items': len([p for p in products if p[10] and int(p[10]) < 5]),
        'suppliers': 1,
        'brands_count': len(brands),
        'colors_count': len(colors),
        'types_count': len(product_types),
        'categories_count': len(trader_categories),
        'tags_count': len(tags)
    }
    
    return render_template('dashboard.html', stats=stats)

# صفحات إدارة البراندات
@app.route('/manage_brands')
def manage_brands():
    brands = db.get_all_brands()
    return render_template('manage_brands.html', brands=brands)

@app.route('/add_brand', methods=['POST'])
def add_brand():
    brand_name = request.form['brand_name'].strip()
    if brand_name:
        if db.add_brand(brand_name):
            flash(f'Brand "{brand_name}" added successfully!', 'success')
        else:
            flash(f'Error: Brand "{brand_name}" already exists!', 'error')
    return redirect(url_for('manage_brands'))

@app.route('/edit_brand/<int:brand_id>', methods=['POST'])
def edit_brand(brand_id):
    new_name = request.form['brand_name'].strip()
    if new_name:
        if db.update_brand(brand_id, new_name):
            flash(f'Brand updated to "{new_name}" successfully!', 'success')
        else:
            flash('Error updating brand - name might already exist!', 'error')
    return redirect(url_for('manage_brands'))

@app.route('/delete_brand/<int:brand_id>', methods=['POST'])
def delete_brand(brand_id):
    success, message = db.delete_brand(brand_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('manage_brands'))

# صفحات إدارة الألوان
@app.route('/manage_colors')
def manage_colors():
    colors = db.get_all_colors()
    return render_template('manage_colors.html', colors=colors)

@app.route('/add_color', methods=['POST'])
def add_color():
    color_name = request.form['color_name'].strip()
    color_code = request.form['color_code']
    if color_name:
        if db.add_color(color_name, color_code):
            flash(f'Color "{color_name}" added successfully!', 'success')
        else:
            flash(f'Error: Color "{color_name}" already exists!', 'error')
    return redirect(url_for('manage_colors'))

@app.route('/edit_color/<int:color_id>', methods=['POST'])
def edit_color(color_id):
    new_name = request.form['color_name'].strip()
    new_code = request.form['color_code'].strip()
    if new_name and new_code:
        if db.update_color(color_id, new_name, new_code):
            flash(f'Color updated to "{new_name}" successfully!', 'success')
        else:
            flash('Error updating color - name might already exist!', 'error')
    return redirect(url_for('manage_colors'))

@app.route('/delete_color/<int:color_id>', methods=['POST'])
def delete_color(color_id):
    success, message = db.delete_color(color_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('manage_colors'))

# صفحات إدارة أنواع المنتجات
@app.route('/manage_product_types')
def manage_product_types():
    product_types = db.get_all_product_types()
    return render_template('manage_product_types.html', product_types=product_types)

@app.route('/add_product_type', methods=['POST'])
def add_product_type():
    type_name = request.form['type_name'].strip()
    if type_name:
        if db.add_product_type(type_name):
            flash(f'Product Type "{type_name}" added successfully!', 'success')
        else:
            flash(f'Error: Product Type "{type_name}" already exists!', 'error')
    return redirect(url_for('manage_product_types'))

@app.route('/edit_product_type/<int:type_id>', methods=['POST'])
def edit_product_type(type_id):
    new_name = request.form['type_name'].strip()
    if new_name:
        if db.update_product_type(type_id, new_name):
            flash(f'Product Type updated to "{new_name}" successfully!', 'success')
        else:
            flash('Error updating product type - name might already exist!', 'error')
    return redirect(url_for('manage_product_types'))

@app.route('/delete_product_type/<int:type_id>', methods=['POST'])
def delete_product_type(type_id):
    success, message = db.delete_product_type(type_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('manage_product_types'))

# صفحات إدارة فئات التجار
@app.route('/manage_trader_categories')
def manage_trader_categories():
    categories = db.get_all_trader_categories()
    return render_template('manage_trader_categories.html', categories=categories)

@app.route('/add_trader_category', methods=['POST'])
def add_trader_category():
    category_code = request.form['category_code'].strip().upper()
    category_name = request.form['category_name'].strip()
    description = request.form['description'].strip()
    
    if category_code and category_name:
        if db.add_trader_category(category_code, category_name, description):
            flash(f'Trader Category "{category_code}" added successfully!', 'success')
        else:
            flash(f'Error: Category code "{category_code}" already exists!', 'error')
    return redirect(url_for('manage_trader_categories'))

@app.route('/edit_trader_category/<int:category_id>', methods=['POST'])
def edit_trader_category(category_id):
    new_code = request.form['category_code'].strip().upper()
    new_name = request.form['category_name'].strip()
    new_description = request.form['description'].strip()
    
    if new_code and new_name:
        if db.update_trader_category(category_id, new_code, new_name, new_description):
            flash(f'Trader Category updated successfully!', 'success')
        else:
            flash('Error updating trader category!', 'error')
    return redirect(url_for('manage_trader_categories'))

@app.route('/delete_trader_category/<int:category_id>', methods=['POST'])
def delete_trader_category(category_id):
    success, message = db.delete_trader_category(category_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('manage_trader_categories'))

# صفحات إدارة Tags
@app.route('/manage_tags')
def manage_tags():
    """صفحة إدارة Tags"""
    tags = db.get_all_tags()
    categories = db.get_tags_by_category()
    return render_template('manage_tags.html', tags=tags, categories=categories)

@app.route('/add_tag', methods=['POST'])
def add_tag():
    """إضافة Tag جديد"""
    tag_name = request.form['tag_name'].strip()
    tag_category = request.form['tag_category'].strip()
    tag_color = request.form['tag_color']
    description = request.form['description'].strip()
    
    if tag_name:
        if db.add_tag(tag_name, tag_category, tag_color, description):
            flash(f'Tag "{tag_name}" added successfully!', 'success')
        else:
            flash(f'Error: Tag "{tag_name}" already exists!', 'error')
    return redirect(url_for('manage_tags'))

@app.route('/edit_tag/<int:tag_id>', methods=['POST'])
def edit_tag(tag_id):
    """تعديل Tag"""
    new_name = request.form['tag_name'].strip()
    new_category = request.form['tag_category'].strip()
    new_color = request.form['tag_color']
    new_description = request.form['description'].strip()
    
    if new_name:
        if db.update_tag(tag_id, new_name, new_category, new_color, new_description):
            flash(f'Tag updated to "{new_name}" successfully!', 'success')
        else:
            flash('Error updating tag - name might already exist!', 'error')
    return redirect(url_for('manage_tags'))

@app.route('/delete_tag/<int:tag_id>', methods=['POST'])
def delete_tag(tag_id):
    """حذف Tag"""
    success, message = db.delete_tag(tag_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('manage_tags'))

# صفحات المنتجات مع النظام المحدث
@app.route('/add_product_new', methods=['GET', 'POST'])
def add_product_new():
    """صفحة إضافة منتج واحد مع المقاس والـ Tags والصور المنظمة"""
    if request.method == 'POST':
        try:
            product_code = request.form['product_code'].strip()
            brand_id = int(request.form['brand_id'])
            product_type_id = int(request.form['product_type_id'])
            trader_category = request.form['trader_category']
            product_size = request.form['product_size'].strip()
            wholesale_price = float(request.form['wholesale_price'])
            retail_price = float(request.form['retail_price'])
            initial_stock = int(request.form.get('initial_stock', 0))
            
            color_ids = request.form.getlist('color_ids')
            color_ids = [int(c) for c in color_ids if c]
            
            tag_ids = request.form.getlist('tag_ids')
            tag_ids = [int(t) for t in tag_ids if t]
            
            if not color_ids:
                flash('Please select at least one color!', 'error')
                return redirect(url_for('add_product_new'))
            
            if db.check_product_exists(product_code, brand_id, trader_category):
                flash('Product with same code, brand, and category already exists!', 'error')
                return redirect(url_for('add_product_new'))
            
            # إضافة المنتج مع المقاس والـ Tags
            success, result = db.add_base_product_with_variants(
                product_code, brand_id, product_type_id, trader_category, product_size,
                wholesale_price, retail_price, color_ids, tag_ids, initial_stock
            )
            
            if success:
                base_product_id = result
                
                # رفع الصور لكل لون مع النظام المنظم
                uploaded_images = 0
                for color_id in color_ids:
                    file_key = f'color_image_{color_id}'
                    if file_key in request.files:
                        file = request.files[file_key]
                        if file and file.filename != '' and allowed_file(file.filename):
                            
                            # جلب اسم اللون
                            color_name = db.get_color_name_by_id(color_id)
                            
                            if color_name:
                                # حفظ الصورة بالنظام المنظم الجديد
                                image_path = db.save_manual_image(file, product_code, color_name)
                                
                                if image_path:
                                    # جلب variant_id
                                    conn = db.get_connection()
                                    cursor = conn.cursor()
                                    cursor.execute('''
                                        SELECT id FROM product_variants 
                                        WHERE base_product_id = ? AND color_id = ?
                                    ''', (base_product_id, color_id))
                                    variant_result = cursor.fetchone()
                                    conn.close()
                                    
                                    if variant_result:
                                        variant_id = variant_result[0]
                                        filename = os.path.basename(image_path)
                                        if db.add_color_image(variant_id, image_path, filename):
                                            uploaded_images += 1
                
                flash(f'Product "{product_code}" added successfully with {len(color_ids)} colors, {len(tag_ids)} tags and {uploaded_images} images!', 'success')
                return redirect(url_for('products_new'))
            else:
                flash(f'Error adding product: {result}', 'error')
                
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    brands = db.get_all_brands()
    colors = db.get_all_colors()
    product_types = db.get_all_product_types()
    trader_categories = db.get_all_trader_categories()
    tags = db.get_all_tags()
    
    return render_template('add_product_new.html', 
                         brands=brands, 
                         colors=colors, 
                         product_types=product_types,
                         trader_categories=trader_categories,
                         tags=tags)

@app.route('/add_products_multi', methods=['GET', 'POST'])
def add_products_multi():
    """صفحة إضافة منتجات متعددة مع المقاس والـ Tags"""
    if request.method == 'POST':
        try:
            num_products = int(request.form.get('num_products', 1))
            
            products_data = []
            
            for i in range(num_products):
                product_code = request.form.get(f'product_code_{i}', '').strip()
                if not product_code:
                    continue
                
                brand_id = request.form.get(f'brand_id_{i}')
                product_type_id = request.form.get(f'product_type_id_{i}')
                trader_category = request.form.get(f'trader_category_{i}')
                product_size = request.form.get(f'product_size_{i}', '').strip()
                wholesale_price = request.form.get(f'wholesale_price_{i}')
                retail_price = request.form.get(f'retail_price_{i}')
                initial_stock = request.form.get(f'initial_stock_{i}', 0)
                
                color_ids = request.form.getlist(f'color_ids_{i}')
                color_ids = [int(c) for c in color_ids if c]
                
                tag_ids = request.form.getlist(f'tag_ids_{i}')
                tag_ids = [int(t) for t in tag_ids if t]
                
                if not color_ids:
                    flash(f'Product {i+1}: Please select at least one color!', 'error')
                    continue
                
                if not brand_id or not product_type_id or not trader_category or not wholesale_price or not retail_price:
                    flash(f'Product {i+1}: Please fill all required fields!', 'error')
                    continue
                
                products_data.append({
                    'product_code': product_code,
                    'brand_id': int(brand_id),
                    'product_type_id': int(product_type_id),
                    'trader_category': trader_category,
                    'product_size': product_size,
                    'wholesale_price': float(wholesale_price),
                    'retail_price': float(retail_price),
                    'initial_stock': int(initial_stock),
                    'color_ids': color_ids,
                    'tag_ids': tag_ids
                })
            
            if not products_data:
                flash('No valid products to add!', 'error')
                return redirect(url_for('add_products_multi'))
            
            result = db.add_multiple_products_batch(products_data)
            
            if result['success']:
                if result['success_count'] > 0:
                    flash(f'Successfully added {result["success_count"]} products!', 'success')
                
                if result['failed_count'] > 0:
                    flash(f'{result["failed_count"]} products failed to add. Check details below.', 'warning')
                    for failed in result['failed_products']:
                        flash(f'Failed to add product {failed["product"]["product_code"]}: {failed["error"]}', 'error')
                
                return redirect(url_for('products_new'))
            else:
                flash(f'Error adding products: {result["error"]}', 'error')
                
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    brands = db.get_all_brands()
    colors = db.get_all_colors()
    product_types = db.get_all_product_types()
    trader_categories = db.get_all_trader_categories()
    tags = db.get_all_tags()
    
    return render_template('add_products_multi.html', 
                         brands=brands, 
                         colors=colors, 
                         product_types=product_types,
                         trader_categories=trader_categories,
                         tags=tags)

@app.route('/products_new')
def products_new():
    """صفحة عرض المنتجات المحسنة مع المقاس والـ Tags والصور"""
    search_term = request.args.get('search', '')
    products = db.get_products_with_color_images(search_term)
    return render_template('products_new.html', products=products, search_term=search_term)

@app.route('/search_products')
def search_products():
    """البحث في المنتجات - AJAX مع المقاس والـ Tags"""
    search_term = request.args.get('q', '')
    products = db.get_products_with_color_images(search_term)
    
    results = []
    for product in products:
        # تحضير بيانات الألوان مع المخزون
        colors_with_stock = []
        for color in product[10]:  # colors_data
            colors_with_stock.append(f"{color['name']}: {color['stock']}")
        
        # تحضير بيانات Tags
        tags_list = [tag[1] for tag in product[12]] if product[12] else []
        
        results.append({
            'id': product[0],
            'code': product[1],
            'brand': product[2],
            'type': product[3],
            'category': product[4],
            'size': product[5],
            'wholesale': product[6],
            'retail': product[7],
            'supplier': product[8],
            'colors_data': product[10],
            'colors_text': ', '.join(colors_with_stock),
            'total_stock': product[11],
            'tags': tags_list,
            'created': product[9][:10] if product[9] else 'N/A'
        })
    
    return jsonify({'products': results})

@app.route('/product_details/<int:product_id>')
def product_details(product_id):
    """صفحة تفاصيل منتج واحد مع الصور والمقاس والـ Tags"""
    details = db.get_product_details(product_id)
    
    if not details:
        flash('Product not found!', 'error')
        return redirect(url_for('products_new'))
    
    return render_template('product_details.html', details=details)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    """حذف منتج مع كل بياناته"""
    success, message = db.delete_product(product_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(f'Error: {message}', 'error')
    
    return redirect(url_for('products_new'))

# صفحات الجرد الشامل مع المقاس والـ Tags
@app.route('/inventory_management')
def inventory_management():
    """صفحة الجرد الشاملة مع المقاس والـ Tags"""
    search_term = request.args.get('search', '')
    brand_filter = request.args.get('brand', '')
    category_filter = request.args.get('category', '')
    
    inventory_data = db.get_all_products_for_inventory(search_term, brand_filter, category_filter)
    summary = db.get_inventory_summary()
    brands = db.get_brands_for_filter()
    categories = db.get_categories_for_filter()
    
    return render_template('inventory_management.html', 
                         inventory_data=inventory_data,
                         summary=summary,
                         brands=brands,
                         categories=categories,
                         search_term=search_term,
                         brand_filter=brand_filter,
                         category_filter=category_filter)

@app.route('/update_inventory', methods=['POST'])
def update_inventory():
    """تحديث المخزون بشكل جماعي"""
    try:
        stock_updates = []
        
        for key, value in request.form.items():
            if key.startswith('stock_'):
                variant_id = key.replace('stock_', '')
                new_stock = int(value) if value.isdigit() else 0
                
                stock_updates.append({
                    'variant_id': int(variant_id),
                    'new_stock': new_stock
                })
        
        if not stock_updates:
            flash('No stock updates to process!', 'warning')
            return redirect(url_for('inventory_management'))
        
        result = db.bulk_update_inventory(stock_updates)
        
        if result['success']:
            flash(f'Successfully updated {result["updated_count"]} items!', 'success')
            if result['failed_count'] > 0:
                flash(f'{result["failed_count"]} items failed to update.', 'warning')
        else:
            flash(f'Error updating inventory: {result["error"]}', 'error')
    
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('inventory_management'))

@app.route('/inventory_search')
def inventory_search():
    """البحث في صفحة الجرد - AJAX"""
    search_term = request.args.get('q', '')
    brand_filter = request.args.get('brand', '')
    category_filter = request.args.get('category', '')
    
    inventory_data = db.get_all_products_for_inventory(search_term, brand_filter, category_filter)
    
    results = []
    for item in inventory_data:
        product = item['product']
        color_variants = item['color_variants']
        
        results.append({
            'product_id': product[0],
            'product_code': product[1],
            'brand': product[2],
            'type': product[3],
            'category': product[4],
            'size': product[5],
            'total_stock': item['total_stock'],
            'tags': [tag[1] for tag in item['tags']],
            'color_variants': [
                {
                    'variant_id': cv[0],
                    'color_id': cv[1],
                    'color_name': cv[2],
                    'color_code': cv[3],
                    'current_stock': cv[4]
                } for cv in color_variants
            ]
        })
    
    return jsonify({'inventory_data': results})

# صفحات Excel Bulk Upload مع النظام المحدث
@app.route('/bulk_upload_excel', methods=['GET', 'POST'])
def bulk_upload_excel():
    """رفع منتجات من Excel مع تحسين الأداء ومعالجة Timeout"""
    if request.method == 'POST':
        try:
            # التحقق من وجود الملف
            if 'excel_file' not in request.files:
                flash('لم يتم اختيار ملف!', 'error')
                return redirect(url_for('bulk_upload_excel'))
            
            file = request.files['excel_file']
            if not file or file.filename == '':
                flash('يرجى اختيار ملف Excel!', 'error')
                return redirect(url_for('bulk_upload_excel'))
            
            # التحقق من نوع الملف
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                flash('يرجى رفع ملف Excel صحيح (.xlsx أو .xls)!', 'error')
                return redirect(url_for('bulk_upload_excel'))

            print(f"🔄 بدء معالجة الملف: {file.filename}")
            
            # قراءة الملف مع تحديد نوع البيانات كـ string لتجنب مشاكل float
            df = pd.read_excel(file, dtype=str)
            print(f"📊 تم قراءة {len(df)} صف من الملف")
            
            # التحقق من وجود الأعمدة المطلوبة
            required_columns = ['Product Code', 'Brand Name', 'Product Type', 'Category',
                              'Wholesale Price', 'Retail Price', 'Color Name', 'Stock']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                flash(f'أعمدة مفقودة في الملف: {", ".join(missing_columns)}', 'error')
                return redirect(url_for('bulk_upload_excel'))

            # تحديد حد أقصى للصفوف لتجنب timeout
            MAX_ROWS = 200
            if len(df) > MAX_ROWS:
                flash(f'الملف كبير جداً! الحد الأقصى {MAX_ROWS} صف. ملفك يحتوي على {len(df)} صف.', 'warning')
                df = df.head(MAX_ROWS)
                flash(f'سيتم معالجة أول {MAX_ROWS} صف فقط.', 'info')

            # تحويل البيانات لقاموس
            excel_data = df.to_dict('records')
            print(f"📦 بدء معالجة {len(excel_data)} منتج...")

            # معالجة البيانات
            result = db.bulk_add_products_from_excel_enhanced(excel_data)

            if result['success']:
                # إنشاء نسخة احتياطية فورية بعد النجاح
                print("🔄 إنشاء نسخة احتياطية فورية بعد Bulk Upload...")
                import time
                time.sleep(2)  # تأخير قصير لضمان اكتمال العمليات
                backup_success = backup_system.create_backup()
                
                if backup_success:
                    print("✅ تم إنشاء النسخة الاحتياطية بنجاح")
                else:
                    print("⚠️ فشل في إنشاء النسخة الاحتياطية")
                
                # رسائل النجاح
                success_msg = f'تم معالجة {result["success_count"]} صف بنجاح من أصل {len(excel_data)}!'
                flash(success_msg, 'success')
                
                # معلومات البيانات الجديدة
                if result['created_brands']:
                    flash(f'تم إنشاء براندات جديدة: {", ".join(result["created_brands"])}', 'info')
                if result['created_colors']:
                    flash(f'تم إنشاء ألوان جديدة: {", ".join(result["created_colors"])}', 'info')
                if result['created_types']:
                    flash(f'تم إنشاء أنواع منتجات جديدة: {", ".join(result["created_types"])}', 'info')

                # تحذيرات في حالة فشل بعض الصفوف
                if result['failed_count'] > 0:
                    flash(f'{result["failed_count"]} صف فشل في المعالجة. راجع التفاصيل أدناه.', 'warning')
                    
                    # عرض أول 5 أخطاء فقط لتجنب ازدحام الرسائل
                    for failed in result['failed_products'][:5]:
                        flash(f'الصف {failed["row"]}: {failed["error"]}', 'error')
                    
                    if len(result['failed_products']) > 5:
                        flash(f'و {len(result["failed_products"]) - 5} أخطاء أخرى...', 'warning')

                return redirect(url_for('products_new'))
            
            else:
                error_msg = result.get('error', 'خطأ غير معروف')
                flash(f'فشل في معالجة الملف: {error_msg}', 'error')
                print(f"❌ فشل في معالجة الملف: {error_msg}")

        except pd.errors.EmptyDataError:
            flash('الملف فارغ أو لا يحتوي على بيانات صالحة!', 'error')
        except pd.errors.ParserError:
            flash('خطأ في قراءة الملف! تأكد من أنه ملف Excel صحيح.', 'error')
        except MemoryError:
            flash('الملف كبير جداً ولا يمكن معالجته. جرب ملف أصغر.', 'error')
        except Exception as e:
            error_msg = str(e)
            flash(f'خطأ في معالجة الملف: {error_msg}', 'error')
            print(f"❌ خطأ عام في bulk upload: {error_msg}")

    # عرض الصفحة
    return render_template('bulk_upload_excel.html')

@app.route('/download_excel_template')
def download_excel_template():
    """تحميل نموذج Excel المحسن - نسخة مبسطة بدون تنسيق"""
    try:
        template_data = {
            'Product Code': ['96115', '96115', '96115', '87432', '87432', '75321'],
            'Brand Name': ['Tommy Hilfiger', 'Tommy Hilfiger', 'Tommy Hilfiger', 'Gucci', 'Gucci', 'Zara'],
            'Product Type': ['Handbag', 'Handbag', 'Handbag', 'Wallet', 'Wallet', 'Backpack'],
            'Category': ['L', 'L', 'L', 'F', 'F', 'L'],
            'Size': ['20×22×5', '20×22×5', '20×22×5', '15×18×3', '15×18×3', '25×30×10'],
            'Wholesale Price': [1000, 1000, 1000, 1200, 1200, 800],
            'Retail Price': [1500, 1500, 1500, 1800, 1800, 1200],
            'Color Name': ['Black', 'Red', 'Brown', 'Gold', 'Silver', 'Navy Blue'],
            'Stock': [15, 5, 3, 10, 8, 20],
            'Image URL': [
                'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400',
                'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400',
                'https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=400',
                'https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400',
                'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400',
                'https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?w=400'
            ],
            'Tags': ['Sale,Medium', 'Sale,Medium', 'Sale,Medium', 'New Arrival,Small', 'New Arrival,Small', 'Summer,Large']
        }
        
        df = pd.DataFrame(template_data)
        
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='products_template_enhanced_v2.xlsx'
        )
        
    except Exception as e:
        print(f"Error creating template: {e}")
        flash('Error creating template file', 'error')
        return redirect(url_for('bulk_upload_excel'))

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    """تعديل بيانات المنتج الأساسية - كل البيانات قابلة للتعديل"""
    if request.method == 'POST':
        try:
            # جلب البيانات الجديدة (كلها قابلة للتعديل)
            product_code = request.form['product_code'].strip()
            brand_id = int(request.form['brand_id'])
            product_type_id = int(request.form['product_type_id'])
            trader_category = request.form['trader_category']
            product_size = request.form.get('product_size', '').strip()
            wholesale_price = float(request.form['wholesale_price'])
            retail_price = float(request.form['retail_price'])
            
            # التحقق من عدم التكرار (إذا تغير الكود/البراند/الفئة)
            old_details = db.get_product_details(product_id)
            old_code = old_details['product'][1]
            old_category = old_details['product'][2]
            
            # جلب brand_id القديم
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT brand_id FROM base_products WHERE id = ?', (product_id,))
            old_brand_id = cursor.fetchone()[0]
            conn.close()
            
            # إذا تغير الكود أو البراند أو الفئة، نتحقق من التكرار
            if (product_code != old_code or brand_id != old_brand_id or trader_category != old_category):
                if db.check_product_exists(product_code, brand_id, trader_category):
                    flash('Product with same code, brand, and category already exists!', 'error')
                    return redirect(url_for('edit_product', product_id=product_id))
            
            # تحديث المنتج
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE base_products 
                SET product_code = ?, brand_id = ?, product_type_id = ?, 
                    trader_category = ?, product_size = ?, wholesale_price = ?, retail_price = ?
                WHERE id = ?
            ''', (product_code, brand_id, product_type_id, trader_category, 
                  product_size, wholesale_price, retail_price, product_id))
            conn.commit()
            conn.close()
            
            flash('Product updated successfully!', 'success')
            return redirect(url_for('product_details', product_id=product_id))
            
        except Exception as e:
            flash(f'Error updating product: {str(e)}', 'error')
    
    # جلب بيانات المنتج للعرض في النموذج
    details = db.get_product_details(product_id)
    if not details:
        flash('Product not found!', 'error')
        return redirect(url_for('products_new'))
    
    brands = db.get_all_brands()
    product_types = db.get_all_product_types()
    trader_categories = db.get_all_trader_categories()
    tags = db.get_all_tags()
    
    return render_template('edit_product.html', 
                         details=details, 
                         brands=brands,
                         product_types=product_types,
                         trader_categories=trader_categories,
                         tags=tags)


@app.route('/update_stock/<int:variant_id>', methods=['POST'])
def update_stock(variant_id):
    """تحديث مخزون لون معين"""
    try:
        new_stock = int(request.form['new_stock'])
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE product_variants SET current_stock = ? WHERE id = ?', 
                      (new_stock, variant_id))
        conn.commit()
        conn.close()
        
        flash('Stock updated successfully!', 'success')
        
    except Exception as e:
        flash(f'Error updating stock: {str(e)}', 'error')
    
    # الرجوع للمنتج
    product_id = request.form.get('product_id')
    return redirect(url_for('product_details', product_id=product_id))

@app.route('/upload_color_image/<int:variant_id>', methods=['POST'])
def upload_color_image(variant_id):
    """رفع صورة جديدة للون"""
    try:
        if 'image_file' not in request.files:
            flash('No image file selected!', 'error')
            return redirect(request.referrer)
        
        file = request.files['image_file']
        if file.filename == '':
            flash('No image file selected!', 'error')
            return redirect(request.referrer)
        
        if file and allowed_file(file.filename):
            # جلب بيانات المنتج واللون
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT bp.product_code, c.color_name 
                FROM product_variants pv
                JOIN base_products bp ON pv.base_product_id = bp.id
                JOIN colors c ON pv.color_id = c.id
                WHERE pv.id = ?
            ''', (variant_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                product_code, color_name = result
                
                # حفظ الصورة بالنظام المنظم
                image_path = db.save_manual_image(file, product_code, color_name)
                
                if image_path:
                    # تحديث رابط الصورة في قاعدة البيانات
                    filename = os.path.basename(image_path)
                    if db.add_color_image(variant_id, image_path, filename):
                        flash('Image uploaded successfully!', 'success')
                    else:
                        flash('Error saving image to database!', 'error')
                else:
                    flash('Error saving image file!', 'error')
            else:
                flash('Variant not found!', 'error')
        else:
            flash('Invalid file type!', 'error')
            
    except Exception as e:
        flash(f'Error uploading image: {str(e)}', 'error')
    
    return redirect(request.referrer)

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# إضافة health check endpoint
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    print(f"🚀 Starting on Render...")
    print(f"📊 Port: {port}")
    print(f"🔧 Debug: {debug}")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
