from flask import Flask, request, render_template
import pandas as pd

app = Flask(__name__)

# PST quarters: Q1=Mar-May, Q2=Jun-Aug, Q3=Sep-Nov, Q4=Dec-Feb
PST_QUARTERS = {
    1: (3, 5),
    2: (6, 8),
    3: (9, 11),
    4: (12, 2),
}

# GST quarters: standard calendar quarters
GST_QUARTERS = {
    1: (1, 3),
    2: (4, 6),
    3: (7, 9),
    4: (10, 12),
}

MONTH_DAYS = {1:31, 2:28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}

def month_to_quarter(month, quarters):
    for q, (start, end) in quarters.items():
        if start <= end:
            if start <= month <= end:
                return q
        else:  # wraps year (Dec-Feb)
            if month >= start or month <= end:
                return q
    return None

def quarter_date_range(year, quarter, quarters):
    start_month, end_month = quarters[quarter]
    if start_month > end_month:  # Q4 PST: Dec-Feb spans two years
        start = f"{year}-{start_month:02d}-01+00:00"
        end = f"{year + 1}-{end_month:02d}-{MONTH_DAYS[end_month]:02d}+00:00"
    else:
        start = f"{year}-{start_month:02d}-01+00:00"
        end = f"{year}-{end_month:02d}-{MONTH_DAYS[end_month]:02d}+00:00"
    return start, end

def detect_year_quarter(df, quarters):
    dates = pd.to_datetime(df['Shipment_Date'].str.replace(r'\+.*', '', regex=True), errors='coerce').dropna()
    if dates.empty:
        return None, None
    dominant_month = dates.dt.month.mode()[0]
    dominant_year = dates.dt.year.mode()[0]
    quarter = month_to_quarter(dominant_month, quarters)
    # For PST Q4 (Dec-Feb), fiscal year is the December year
    start_month = quarters[quarter][0]
    if start_month > quarters[quarter][1] and dominant_month <= 2:
        dominant_year -= 1
    return dominant_year, quarter

def quarter_label(year, quarter, quarters):
    start_month, end_month = quarters[quarter]
    if start_month > end_month:
        s = pd.Timestamp(year, start_month, 1).strftime('%b')
        e = pd.Timestamp(year + 1, end_month, 1).strftime('%b')
        return f"{s} {year} – {e} {year + 1}"
    s = pd.Timestamp(year, start_month, 1).strftime('%b')
    e = pd.Timestamp(year, end_month, 1).strftime('%b')
    return f"{s} – {e} {year}"

def detect_year(df):
    dates = pd.to_datetime(df['Shipment_Date'].str.replace(r'\+.*', '', regex=True), errors='coerce').dropna()
    if dates.empty:
        return None
    return int(dates.dt.year.mode()[0])

@app.route('/', methods=['GET', 'POST'])
def index():
    pst_result = None
    gst_result = None
    qst_result = None
    pst_error = None
    gst_error = None
    qst_error = None

    if request.method == 'POST':
        calc_type = request.form.get('calc_type')
        file = request.files.get('csv_file')

        if not file or file.filename == '':
            error_msg = 'Please upload a CSV file.'
            if calc_type == 'pst':
                pst_error = error_msg
            elif calc_type == 'gst':
                gst_error = error_msg
            else:
                qst_error = error_msg
        else:
            try:
                df = pd.read_csv(file, encoding='latin1')

                if calc_type == 'pst':
                    year, quarter = detect_year_quarter(df, PST_QUARTERS)
                    if year is None:
                        pst_error = 'Could not detect dates from the file.'
                    else:
                        start, end = quarter_date_range(year, quarter, PST_QUARTERS)
                        pst_total = df['Tax_Amount'][df['Tax_Type'] == 'Provincial Sales Tax (PST)'].sum()
                        fil = df[
                            (df['Shipment_Date'] >= start) &
                            (df['Shipment_Date'] <= end) &
                            (df['Tax_Type'] == 'GST/HST')
                        ]
                        sales = fil['TaxExclusive_Selling_Price'].sum()
                        pst_result = {
                            'year': year,
                            'quarter': quarter,
                            'period': quarter_label(year, quarter, PST_QUARTERS),
                            'sales': round(sales, 2),
                            'pst': round(pst_total, 2),
                            'filename': file.filename,
                        }

                elif calc_type == 'gst':
                    year, quarter = detect_year_quarter(df, GST_QUARTERS)
                    if year is None:
                        gst_error = 'Could not detect dates from the file.'
                    else:
                        start, end = quarter_date_range(year, quarter, GST_QUARTERS)
                        fil = df[
                            (df['Shipment_Date'] >= start) &
                            (df['Shipment_Date'] <= end) &
                            (df['Tax_Type'] == 'GST/HST')
                        ]
                        sales = fil['TaxExclusive_Selling_Price'].sum()
                        gst = fil['Tax_Amount'].sum()
                        gst_result = {
                            'year': year,
                            'quarter': quarter,
                            'period': quarter_label(year, quarter, GST_QUARTERS),
                            'sales': round(sales, 2),
                            'gst': round(gst, 2),
                            'filename': file.filename,
                        }

                elif calc_type == 'qst':
                    year = detect_year(df)
                    if year is None:
                        qst_error = 'Could not detect dates from the file.'
                    else:
                        start = f"{year}-01-01+00:00"
                        end = f"{year}-12-31+00:00"
                        gst_fil = df[
                            (df['Shipment_Date'] >= start) &
                            (df['Shipment_Date'] <= end) &
                            (df['Tax_Type'] == 'GST/HST')
                        ]
                        qst_fil = df[
                            (df['Shipment_Date'] >= start) &
                            (df['Shipment_Date'] <= end) &
                            (df['Tax_Type'] == 'Quebec Sales Tax (VAT)')
                        ]
                        sales = gst_fil['TaxExclusive_Selling_Price'].sum()
                        qst = qst_fil['Tax_Amount'].sum()
                        qst_result = {
                            'year': year,
                            'sales': round(sales, 2),
                            'qst': round(qst, 2),
                            'filename': file.filename,
                        }

            except Exception as e:
                error_msg = f'Error processing file: {str(e)}'
                if calc_type == 'pst':
                    pst_error = error_msg
                elif calc_type == 'gst':
                    gst_error = error_msg
                else:
                    qst_error = error_msg

    return render_template('index.html',
                           pst_result=pst_result, pst_error=pst_error,
                           gst_result=gst_result, gst_error=gst_error,
                           qst_result=qst_result, qst_error=qst_error)

if __name__ == '__main__':
    app.run(debug=True)
