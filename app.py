from flask import Flask, request, render_template
import pandas as pd
import re

app = Flask(__name__)

# PST quarters: Q1=Mar-May(3-5), Q2=Jun-Aug(6-8), Q3=Sep-Nov(9-11), Q4=Dec-Feb(12-2)
QUARTERS = {
    1: (3, 5),
    2: (6, 8),
    3: (9, 11),
    4: (12, 2),
}

def month_to_quarter(month):
    for q, (start, end) in QUARTERS.items():
        if start <= end:
            if start <= month <= end:
                return q
        else:  # wraps year (Dec-Feb)
            if month >= start or month <= end:
                return q
    return None

def quarter_date_range(year, quarter):
    start_month, end_month = QUARTERS[quarter]
    if quarter == 4:  # Dec-Feb spans two years
        start = f"{year}-12-01+00:00"
        end = f"{year + 1}-02-28+00:00"
    else:
        end_day = 31 if end_month in (3, 5, 7, 8, 10, 12) else 30
        start = f"{year}-{start_month:02d}-01+00:00"
        end = f"{year}-{end_month:02d}-{end_day}+00:00"
    return start, end

def detect_year_quarter(df):
    """Infer fiscal year and PST quarter from the shipment dates in the file."""
    dates = pd.to_datetime(df['Shipment_Date'].str.replace(r'\+.*', '', regex=True), errors='coerce').dropna()
    if dates.empty:
        return None, None
    # Use the most common month to determine the quarter
    months = dates.dt.month
    dominant_month = months.mode()[0]
    dominant_year = dates.dt.year.mode()[0]
    quarter = month_to_quarter(dominant_month)
    # For Q4 (Dec-Feb), fiscal year is the December year
    if quarter == 4:
        if dominant_month <= 2:
            dominant_year -= 1  # Feb belongs to previous Dec's fiscal year
    return dominant_year, quarter

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    error = None

    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or file.filename == '':
            error = 'Please upload a CSV file.'
        else:
            try:
                df = pd.read_csv(file, encoding='latin1')

                year, quarter = detect_year_quarter(df)
                if year is None:
                    error = 'Could not detect dates from the file.'
                else:
                    start, end = quarter_date_range(year, quarter)

                    pst_total = df['Tax_Amount'][df['Tax_Type'] == 'Provincial Sales Tax (PST)'].sum()

                    fil = df[
                        (df['Shipment_Date'] >= start) &
                        (df['Shipment_Date'] <= end) &
                        (df['Tax_Type'] == 'GST/HST')
                    ]
                    sales = fil['TaxExclusive_Selling_Price'].sum()

                    start_month, end_month = QUARTERS[quarter]
                    result = {
                        'year': year,
                        'quarter': quarter,
                        'period': f"{'Dec' if quarter == 4 else pd.Timestamp(year, start_month, 1).strftime('%b')} – "
                                  f"{'Feb' if quarter == 4 else pd.Timestamp(year, end_month, 1).strftime('%b')} {year if quarter != 4 else f'{year}/{year+1}'}",
                        'sales': round(sales, 2),
                        'pst': round(pst_total, 2),
                        'filename': file.filename,
                    }
            except Exception as e:
                error = f'Error processing file: {str(e)}'

    return render_template('index.html', result=result, error=error)

if __name__ == '__main__':
    app.run(debug=True)
