"""Seed PostgreSQL with mock test data (employees, sales, etc.)."""
import sys
import os
from datetime import datetime, timedelta
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.database.connection import engine
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def create_tables():
    """Create tables for employees, sales, and other test data."""
    logger.info("Creating PostgreSQL tables for test data...")
    
    with engine.connect() as conn:
        # Create employees table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                employee_id VARCHAR(50) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                department VARCHAR(100) NOT NULL,
                position VARCHAR(100) NOT NULL,
                hire_date DATE NOT NULL,
                salary DECIMAL(10, 2),
                manager_id INTEGER,
                location VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create sales table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                sale_id VARCHAR(50) UNIQUE NOT NULL,
                employee_id VARCHAR(50),
                customer_name VARCHAR(255) NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                sale_date DATE NOT NULL,
                amount DECIMAL(12, 2) NOT NULL,
                quantity INTEGER NOT NULL,
                region VARCHAR(100),
                quarter VARCHAR(10),
                year INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE SET NULL
            )
        """))
        
        # Create products table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                product_id VARCHAR(50) UNIQUE NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                cost DECIMAL(10, 2) NOT NULL,
                stock_quantity INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create departments table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS departments (
                id SERIAL PRIMARY KEY,
                department_name VARCHAR(100) UNIQUE NOT NULL,
                head_employee_id VARCHAR(50),
                budget DECIMAL(15, 2),
                location VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.commit()
        logger.info("Tables created successfully")


def seed_employees():
    """Seed employees table with mock data."""
    logger.info("Seeding employees table...")
    
    departments = ["Engineering", "Sales", "Marketing", "Product", "Customer Success", "HR", "Finance", "Operations"]
    positions_by_dept = {
        "Engineering": ["Software Engineer", "Senior Software Engineer", "Engineering Manager", "Staff Engineer", "Principal Engineer"],
        "Sales": ["Account Executive", "Sales Development Rep", "Sales Manager", "VP of Sales"],
        "Marketing": ["Marketing Manager", "Content Writer", "Marketing Analyst", "Brand Manager"],
        "Product": ["Product Manager", "Product Designer", "Product Analyst"],
        "Customer Success": ["Customer Success Manager", "Support Engineer", "Technical Account Manager"],
        "HR": ["HR Manager", "Recruiter", "People Operations"],
        "Finance": ["Financial Analyst", "Accountant", "CFO"],
        "Operations": ["Operations Manager", "Business Analyst", "Operations Coordinator"]
    }
    
    locations = ["San Francisco", "New York", "Austin", "Seattle", "Remote"]
    
    first_names = ["John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Jessica", 
                   "William", "Ashley", "James", "Amanda", "Christopher", "Melissa", "Daniel", "Michelle",
                   "Matthew", "Nicole", "Anthony", "Stephanie", "Mark", "Rachel", "Donald", "Lauren",
                   "Steven", "Kimberly", "Paul", "Lisa", "Andrew", "Nancy", "Joshua", "Karen"]
    
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
                  "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor",
                  "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Sanchez"]
    
    employees_data = []
    employee_ids = []
    
    # Generate employees
    for i in range(150):  # Generate 150 employees
        dept = random.choice(departments)
        position = random.choice(positions_by_dept[dept])
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        email = f"{first_name.lower()}.{last_name.lower()}@techcorp.com"
        employee_id = f"EMP{1000 + i:04d}"
        employee_ids.append(employee_id)
        
        # Hire date in the past 5 years
        hire_date = datetime.now() - timedelta(days=random.randint(0, 1825))
        
        # Salary based on position
        if "Manager" in position or "VP" in position:
            salary = random.randint(120000, 250000)
        elif "Senior" in position or "Staff" in position or "Principal" in position:
            salary = random.randint(150000, 220000)
        else:
            salary = random.randint(80000, 150000)
        
        location = random.choice(locations)
        
        employees_data.append({
            'employee_id': employee_id,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'department': dept,
            'position': position,
            'hire_date': hire_date.date(),
            'salary': salary,
            'manager_id': None,  # Will set managers later
            'location': location
        })
    
    # Set managers (first employee in each department becomes manager)
    dept_managers = {}
    for emp in employees_data:
        if emp['department'] not in dept_managers:
            dept_managers[emp['department']] = emp['employee_id']
        elif "Manager" in emp['position'] or "VP" in emp['position']:
            dept_managers[emp['department']] = emp['employee_id']
    
    for emp in employees_data:
        if emp['employee_id'] != dept_managers.get(emp['department']):
            # Assign manager from same department
            manager_id = dept_managers.get(emp['department'])
            if manager_id:
                emp['manager_id'] = manager_id
    
    # Insert employees
    with engine.connect() as conn:
        # Clear existing data
        conn.execute(text("TRUNCATE TABLE employees CASCADE"))
        
        for emp in employees_data:
            conn.execute(text("""
                INSERT INTO employees (employee_id, first_name, last_name, email, department, 
                                     position, hire_date, salary, manager_id, location)
                VALUES (:employee_id, :first_name, :last_name, :email, :department, 
                       :position, :hire_date, :salary, :manager_id, :location)
            """), emp)
        
        conn.commit()
        logger.info(f"Inserted {len(employees_data)} employees")


def seed_sales():
    """Seed sales table with mock data."""
    logger.info("Seeding sales table...")
    
    # Get employee IDs from sales department
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT employee_id FROM employees WHERE department = 'Sales'
        """))
        sales_employee_ids = [row[0] for row in result]
    
    if not sales_employee_ids:
        logger.warning("No sales employees found, creating sales without employee_id")
        sales_employee_ids = [None]
    
    products = [
        ("Enterprise AI Platform", "Software"),
        ("Data Analytics Suite", "Software"),
        ("Cloud Infrastructure", "Infrastructure"),
        ("Security Solution", "Security"),
        ("API Gateway", "Infrastructure"),
        ("ML Model Service", "AI/ML"),
        ("Customer Portal", "Software"),
        ("Integration Hub", "Platform")
    ]
    
    customers = ["Acme Corp", "GlobalBank", "TechStart Inc", "Enterprise Solutions", "Digital Corp",
                 "Innovation Labs", "Future Systems", "Smart Business", "Data Dynamics", "Cloud First",
                 "AI Ventures", "NextGen Tech", "Scale Systems", "Modern Enterprises", "Digital Partners"]
    
    regions = ["North America", "Europe", "Asia Pacific", "Latin America"]
    
    sales_data = []
    
    # Generate sales for the past 2 years
    start_date = datetime.now() - timedelta(days=730)
    
    for i in range(500):  # Generate 500 sales records
        sale_date = start_date + timedelta(days=random.randint(0, 730))
        product_name, category = random.choice(products)
        customer = random.choice(customers)
        employee_id = random.choice(sales_employee_ids) if sales_employee_ids else None
        
        # Amount based on product
        base_amounts = {
            "Enterprise AI Platform": (50000, 200000),
            "Data Analytics Suite": (30000, 150000),
            "Cloud Infrastructure": (20000, 100000),
            "Security Solution": (40000, 180000),
            "API Gateway": (25000, 120000),
            "ML Model Service": (60000, 250000),
            "Customer Portal": (15000, 80000),
            "Integration Hub": (35000, 140000)
        }
        
        min_amount, max_amount = base_amounts.get(product_name, (20000, 100000))
        amount = random.randint(min_amount, max_amount)
        quantity = random.randint(1, 5)
        
        # Calculate quarter
        quarter = f"Q{(sale_date.month - 1) // 3 + 1}"
        year = sale_date.year
        region = random.choice(regions)
        
        sale_id = f"SALE{2024000 + i:04d}"
        
        sales_data.append({
            'sale_id': sale_id,
            'employee_id': employee_id,
            'customer_name': customer,
            'product_name': product_name,
            'sale_date': sale_date.date(),
            'amount': amount,
            'quantity': quantity,
            'region': region,
            'quarter': quarter,
            'year': year
        })
    
    # Insert sales
    with engine.connect() as conn:
        # Clear existing data
        conn.execute(text("TRUNCATE TABLE sales"))
        
        for sale in sales_data:
            conn.execute(text("""
                INSERT INTO sales (sale_id, employee_id, customer_name, product_name, sale_date,
                                 amount, quantity, region, quarter, year)
                VALUES (:sale_id, :employee_id, :customer_name, :product_name, :sale_date,
                       :amount, :quantity, :region, :quarter, :year)
            """), sale)
        
        conn.commit()
        logger.info(f"Inserted {len(sales_data)} sales records")


def seed_products():
    """Seed products table with mock data."""
    logger.info("Seeding products table...")
    
    products_data = [
        ("PROD001", "Enterprise AI Platform", "Software", 100000, 40000, 50),
        ("PROD002", "Data Analytics Suite", "Software", 75000, 30000, 100),
        ("PROD003", "Cloud Infrastructure", "Infrastructure", 50000, 20000, 200),
        ("PROD004", "Security Solution", "Security", 90000, 35000, 75),
        ("PROD005", "API Gateway", "Infrastructure", 60000, 25000, 150),
        ("PROD006", "ML Model Service", "AI/ML", 120000, 50000, 30),
        ("PROD007", "Customer Portal", "Software", 40000, 15000, 120),
        ("PROD008", "Integration Hub", "Platform", 70000, 28000, 80),
    ]
    
    with engine.connect() as conn:
        # Clear existing data
        conn.execute(text("TRUNCATE TABLE products"))
        
        for prod in products_data:
            conn.execute(text("""
                INSERT INTO products (product_id, product_name, category, price, cost, stock_quantity)
                VALUES (:product_id, :product_name, :category, :price, :cost, :stock_quantity)
            """), {
                'product_id': prod[0],
                'product_name': prod[1],
                'category': prod[2],
                'price': prod[3],
                'cost': prod[4],
                'stock_quantity': prod[5]
            })
        
        conn.commit()
        logger.info(f"Inserted {len(products_data)} products")


def seed_departments():
    """Seed departments table with mock data."""
    logger.info("Seeding departments table...")
    
    with engine.connect() as conn:
        # Get department heads (first manager/VP from each department)
        result = conn.execute(text("""
            SELECT department, employee_id 
            FROM employees 
            WHERE position LIKE '%Manager%' OR position LIKE '%VP%'
            ORDER BY department, employee_id
        """))
        
        dept_heads = {}
        for row in result:
            dept = row[0]
            if dept not in dept_heads:  # Take first manager/VP for each department
                dept_heads[dept] = row[1]
    
    departments_data = [
        ("Engineering", 5000000),
        ("Sales", 3000000),
        ("Marketing", 2000000),
        ("Product", 2500000),
        ("Customer Success", 1800000),
        ("HR", 800000),
        ("Finance", 1200000),
        ("Operations", 1500000),
    ]
    
    locations = ["San Francisco", "New York", "Austin", "Seattle"]
    
    with engine.connect() as conn:
        # Clear existing data
        conn.execute(text("TRUNCATE TABLE departments"))
        
        for dept_name, budget in departments_data:
            head_id = dept_heads.get(dept_name)
            location = random.choice(locations)
            
            conn.execute(text("""
                INSERT INTO departments (department_name, head_employee_id, budget, location)
                VALUES (:department_name, :head_employee_id, :budget, :location)
            """), {
                'department_name': dept_name,
                'head_employee_id': head_id,
                'budget': budget,
                'location': location
            })
        
        conn.commit()
        logger.info(f"Inserted {len(departments_data)} departments")


def main():
    """Main function to seed PostgreSQL with test data."""
    logger.info("=== Starting PostgreSQL Seeding ===")
    
    try:
        # Create tables
        create_tables()
        
        # Seed data
        seed_employees()
        seed_sales()
        seed_products()
        seed_departments()
        
        # Print summary
        with engine.connect() as conn:
            emp_count = conn.execute(text("SELECT COUNT(*) FROM employees")).scalar()
            sales_count = conn.execute(text("SELECT COUNT(*) FROM sales")).scalar()
            prod_count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
            dept_count = conn.execute(text("SELECT COUNT(*) FROM departments")).scalar()
        
        logger.info("=== PostgreSQL Seeding Complete ===")
        logger.info(f"Employees: {emp_count}")
        logger.info(f"Sales: {sales_count}")
        logger.info(f"Products: {prod_count}")
        logger.info(f"Departments: {dept_count}")
        
    except Exception as e:
        logger.error(f"Error seeding PostgreSQL: {e}")
        raise


if __name__ == "__main__":
    main()
