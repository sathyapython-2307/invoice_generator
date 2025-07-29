from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_mail import Mail, Message
from wtforms import StringField, SubmitField, DecimalField, IntegerField, EmailField, TextAreaField
from wtforms.validators import DataRequired
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
app.config['INVOICE_FOLDER'] = 'invoices'

db = SQLAlchemy(app)
mail = Mail(app)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(20), nullable=False)

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    customer = db.relationship('Customer', backref='invoices')
    total = db.Column(db.Float, nullable=False)
    pdf_path = db.Column(db.String(200), nullable=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    invoice = db.relationship('Invoice', backref='items')

class CustomerForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired()])
    address = TextAreaField('Address', validators=[DataRequired()])
    phone = StringField('Phone', validators=[DataRequired()])
    submit = SubmitField('Save Customer')

class ItemForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired()])
    price = DecimalField('Price', validators=[DataRequired()])
    submit = SubmitField('Add Item')

def generate_pdf(invoice, customer, items):
    filename = f"invoice_{invoice.invoice_number}.pdf"
    filepath = os.path.join(app.config['INVOICE_FOLDER'], filename)
    
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "INVOICE")
    c.setFont("Helvetica", 12)
    c.drawString(72, height - 100, f"Invoice #: {invoice.invoice_number}")
    c.drawString(72, height - 120, f"Date: {invoice.date.strftime('%Y-%m-%d')}")
    
    # Customer Info
    c.drawString(72, height - 160, "Bill To:")
    c.drawString(72, height - 180, customer.name)
    c.drawString(72, height - 200, customer.address)
    c.drawString(72, height - 220, f"Phone: {customer.phone}")
    c.drawString(72, height - 240, f"Email: {customer.email}")
    
    # Items Table
    data = [['Description', 'Qty', 'Price', 'Total']]
    for item in items:
        data.append([item.description, str(item.quantity), f"${item.price:.2f}", f"${item.quantity * item.price:.2f}"])
    
    table = Table(data, colWidths=[300, 50, 80, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    table.wrapOn(c, width - 144, height)
    table.drawOn(c, 72, height - 400)
    
    # Total
    c.setFont("Helvetica-Bold", 14)
    c.drawString(400, height - 450, f"TOTAL: ${invoice.total:.2f}")
    
    # Footer
    c.setFont("Helvetica", 10)
    c.drawString(72, 50, "Thank you for your business!")
    
    c.save()
    return filename

@app.route('/')
def index():
    invoices = Invoice.query.order_by(Invoice.date.desc()).all()
    return render_template('index.html', invoices=invoices)

@app.route('/create_invoice', methods=['GET', 'POST'])
def create_invoice():
    customer_form = CustomerForm()
    item_form = ItemForm()
    items = []
    
    if request.method == 'POST':
        if customer_form.validate_on_submit():
            customer = Customer(
                name=customer_form.name.data,
                email=customer_form.email.data,
                address=customer_form.address.data,
                phone=customer_form.phone.data
            )
            db.session.add(customer)
            db.session.commit()
            flash('Customer saved successfully!', 'success')
        
        if item_form.validate_on_submit():
            items.append({
                'description': item_form.description.data,
                'quantity': item_form.quantity.data,
                'price': item_form.price.data
            })
            flash('Item added!', 'info')
            item_form.description.data = ''
            item_form.quantity.data = ''
            item_form.price.data = ''
        
        if 'generate_invoice' in request.form and items:
            customer = Customer.query.order_by(Customer.id.desc()).first()
            if not customer:
                flash('Please save customer details first', 'danger')
                return redirect(url_for('create_invoice'))
            
            total = sum(item['quantity'] * item['price'] for item in items)
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            invoice = Invoice(
                invoice_number=invoice_number,
                customer_id=customer.id,
                total=total,
                pdf_path=''
            )
            db.session.add(invoice)
            db.session.commit()
            
            for item_data in items:
                item = Item(
                    description=item_data['description'],
                    quantity=item_data['quantity'],
                    price=item_data['price'],
                    invoice_id=invoice.id
                )
                db.session.add(item)
            
            pdf_filename = generate_pdf(invoice, customer, items)
            invoice.pdf_path = pdf_filename
            db.session.commit()
            
            flash('Invoice generated successfully!', 'success')
            return redirect(url_for('view_invoice', invoice_id=invoice.id))
    
    return render_template('create_invoice.html', 
                         customer_form=customer_form, 
                         item_form=item_form, 
                         items=items)

@app.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    return render_template('view_invoice.html', invoice=invoice)

@app.route('/download/<path:filename>')
def download_invoice(filename):
    return send_from_directory(app.config['INVOICE_FOLDER'], filename, as_attachment=True)

@app.route('/email/<int:invoice_id>')
def email_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    customer = invoice.customer
    
    msg = Message(
        subject=f"Invoice {invoice.invoice_number}",
        recipients=[customer.email],
        body=f"Dear {customer.name},\n\nPlease find attached your invoice.\n\nThank you!"
    )
    
    with app.open_resource(os.path.join(app.config['INVOICE_FOLDER'], invoice.pdf_path)) as fp:
        msg.attach(invoice.pdf_path, "application/pdf", fp.read())
    
    mail.send(msg)
    flash('Invoice emailed successfully!', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not os.path.exists(app.config['INVOICE_FOLDER']):
            os.makedirs(app.config['INVOICE_FOLDER'])
    app.run(debug=True)