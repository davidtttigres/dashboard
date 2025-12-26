import os
import json
import gspread
import pandas as pd
import numpy as np
import logging
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# Configure logging
log_filename = os.path.join(os.path.dirname(__file__), '../consolidacion.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)

def get_credentials():
    # Try getting credentials from environment variable first (GitHub Actions)
    env_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    if env_creds:
        logging.info("Using credentials from environment variable.")
        creds_dict = json.loads(env_creds)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Fallback to local file
        logging.info("Using credentials from local file.")
        credentials_path = os.path.join(os.path.dirname(__file__), '../credentials/credentials.json')
        if not os.path.exists(credentials_path):
            logging.error(f"Credentials not found at {credentials_path}")
            raise FileNotFoundError(f"Credentials not found at {credentials_path} or in environment variables.")
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    
    return creds

def clean_currency(x):
    if isinstance(x, str):
        # Format: ' 139.15 € '
        clean_str = x.replace('€', '').replace('$', '').replace(',', '').strip()
        try:
            return float(clean_str)
        except ValueError:
            return 0.0
    return x

def main():
    try:
        logging.info("Starting consolidation process...")
        
        # Configure pandas display
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_rows', 100)

        # Authenticate
        creds = get_credentials()
        client = gspread.authorize(creds)

        # Open spreadsheet
        spreadsheet_url = 'https://docs.google.com/spreadsheets/d/1MiKbS14cgbKEa00QIqX7jqms5PyFc-wru5iHm9EqTeM/edit'
        sh = client.open_by_url(spreadsheet_url)

        # Collect dataframes
        dfs = []
        logging.info("Processing worksheets...")
        for worksheet in sh.worksheets():
            title = worksheet.title
            if title.isdigit() and len(title) == 4:
                logging.info(f"Processing sheet: {title}")
                rows = worksheet.get_all_values()
                if rows:
                    headers = rows[0]
                    df = pd.DataFrame(rows[1:], columns=headers)
                    df = df.loc[:, df.columns != '']
                    df['Year_Source'] = title
                    dfs.append(df)

        if not dfs:
            logging.warning("No year-formatted sheets found.")
            return

        df_consolidado = pd.concat(dfs, ignore_index=True)
        logging.info("Consolidation complete.")

        # Data Cleaning
        logging.info("Cleaning data...")
        df_consolidado['Fecha'] = pd.to_datetime(df_consolidado['Fecha'], dayfirst=False, errors='coerce')
        df_consolidado['Vencimiento'] = pd.to_datetime(df_consolidado['Vencimiento'], dayfirst=False, errors='coerce')
        df_consolidado['Fecha de cobro'] = pd.to_datetime(df_consolidado['Fecha de cobro'], dayfirst=False, errors='coerce')

        if df_consolidado['Total'].dtype == 'object':
            df_consolidado['Total'] = df_consolidado['Total'].apply(clean_currency)
        else:
            df_consolidado['Total'] = pd.to_numeric(df_consolidado['Total'], errors='coerce').fillna(0)

        # Generate Gold Layer
        logging.info("Generating Gold Layer...")
        min_date = df_consolidado['Fecha'].min()
        max_data_date = df_consolidado['Fecha'].max()
        now = datetime.now()
        
        if pd.isna(min_date):
            logging.error("Error: Could not determine min date.")
            return

        max_date = max(max_data_date, now)
        start_date = min_date.replace(day=1)
        current_date = max_date.replace(day=1)
        
        date_range = pd.date_range(start=start_date, end=current_date, freq='MS')
        clients = df_consolidado['Cliente'].unique()
        
        gold_rows = []
        
        for snapshot_date in date_range:
            is_current_month = (snapshot_date.year == now.year) and (snapshot_date.month == now.month)
            
            billing_in_month = df_consolidado[
                (df_consolidado['Fecha'].dt.year == snapshot_date.year) & 
                (df_consolidado['Fecha'].dt.month == snapshot_date.month)
            ]
            
            relevant_invoices_debt = df_consolidado[df_consolidado['Fecha'] <= snapshot_date]
            
            for client in clients:
                # Billing
                client_billing_df = billing_in_month[billing_in_month['Cliente'] == client]
                client_billing = client_billing_df['Total'].sum()
                
                if client_billing > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Facturación Mensual',
                        'Monto': client_billing,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(client_billing_df),
                        'Lista_Facturas': ', '.join(client_billing_df['Num'].astype(str).tolist())
                    })
                
                # Debt
                client_invoices = relevant_invoices_debt[relevant_invoices_debt['Cliente'] == client]
                 
                deuda_lt_3_sum = 0
                deuda_3_6_sum = 0
                deuda_6_12_sum = 0
                deuda_gt_12_sum = 0
                crossed_3_months_sum = 0
                
                paid_debt_post_start_sum = 0
                paid_alert_post_start_sum = 0
                
                list_lt_3 = []
                list_3_6 = []
                list_6_12 = []
                list_gt_12 = []
                list_crossed = []
                list_paid_post_start = []
                list_paid_alert = []
                
                for _, invoice in client_invoices.iterrows():
                    payment_date = invoice['Fecha de cobro']
                    invoice_date = invoice['Fecha']
                    total = invoice['Total']
                    inv_num = str(invoice['Num'])
                    
                    is_unpaid = pd.isna(payment_date) or (payment_date > snapshot_date)
                    
                    if is_unpaid and pd.notna(invoice_date):
                        days_overdue = (snapshot_date - invoice_date).days
                        months_overdue = days_overdue / 30.44
                        
                        if days_overdue > 0:
                            if months_overdue < 3:
                                deuda_lt_3_sum += total
                                list_lt_3.append(inv_num)
                            elif 3 <= months_overdue < 6:
                                deuda_3_6_sum += total
                                list_3_6.append(inv_num)
                            elif 6 <= months_overdue < 12:
                                deuda_6_12_sum += total
                                list_6_12.append(inv_num)
                            elif months_overdue >= 12:
                                deuda_gt_12_sum += total
                                list_gt_12.append(inv_num)
                                
                            prev_month_date = snapshot_date - pd.DateOffset(months=1)
                            days_overdue_prev = (prev_month_date - invoice_date).days
                            months_overdue_prev = days_overdue_prev / 30.44
                            
                            if (months_overdue_prev < 3) and (months_overdue >= 3):
                                crossed_3_months_sum += total
                                list_crossed.append(inv_num)

                            # Check for payments made AFTER the snapshot date (Post-Inicio)
                            # is_unpaid is True means payment_date > snapshot_date OR payment_date is NaT
                            # We only care if payment_date is NOT NaT (actual payment happened)
                            if pd.notna(payment_date):
                                paid_debt_post_start_sum += total
                                list_paid_post_start.append(inv_num)
                                
                                # Check if it was an alert item
                                if (months_overdue_prev < 3) and (months_overdue >= 3):
                                    paid_alert_post_start_sum += total
                                    list_paid_alert.append(inv_num)

                if deuda_lt_3_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Deuda 0-3 Meses',
                        'Monto': deuda_lt_3_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_lt_3),
                        'Lista_Facturas': ', '.join(list_lt_3)
                    })
                if deuda_3_6_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Deuda 3-6 Meses',
                        'Monto': deuda_3_6_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_3_6),
                        'Lista_Facturas': ', '.join(list_3_6)
                    })
                if deuda_6_12_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Deuda 6-12 Meses',
                        'Monto': deuda_6_12_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_6_12),
                        'Lista_Facturas': ', '.join(list_6_12)
                    })
                if deuda_gt_12_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Deuda > 12 Meses',
                        'Monto': deuda_gt_12_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_gt_12),
                        'Lista_Facturas': ', '.join(list_gt_12)
                    })
                if crossed_3_months_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Alerta: Pasó 3 Meses',
                        'Monto': crossed_3_months_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_crossed),
                        'Lista_Facturas': ', '.join(list_crossed)
                    })
                
                if is_current_month and paid_debt_post_start_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Pagos Deuda Post-Inicio',
                        'Monto': paid_debt_post_start_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_paid_post_start),
                        'Lista_Facturas': ', '.join(list_paid_post_start)
                    })
                    
                if is_current_month and paid_alert_post_start_sum > 0:
                    gold_rows.append({
                        'Fecha_Reporte': snapshot_date,
                        'Cliente': client,
                        'Concepto': 'Pagos Alerta Post-Inicio',
                        'Monto': paid_alert_post_start_sum,
                        'Es_Mes_Actual': is_current_month,
                        'Numero_Facturas': len(list_paid_alert),
                        'Lista_Facturas': ', '.join(list_paid_alert)
                    })

        df_gold = pd.DataFrame(gold_rows)
        
        if not df_gold.empty:
            # Sort to ensure proper alignment if we were to use shift, though we are using merge
            df_gold = df_gold.sort_values(by=['Cliente', 'Concepto', 'Fecha_Reporte'])
            
            # Calculate Previous Month Variation
            # Create a temporary dataframe with previous month's dates shifted forward to match current month
            df_prev = df_gold[['Fecha_Reporte', 'Cliente', 'Concepto', 'Monto']].copy()
            df_prev['Fecha_Reporte'] = df_prev['Fecha_Reporte'] + pd.DateOffset(months=1)
            df_prev = df_prev.rename(columns={'Monto': 'Monto_Anterior'})
            
            # Merge to get the previous month's amount on the current row
            df_gold = pd.merge(
                df_gold, 
                df_prev, 
                on=['Fecha_Reporte', 'Cliente', 'Concepto'], 
                how='left'
            )
            
            # Fill NaN for Monto_Anterior with 0 (assuming 0 if no previous record)
            df_gold['Monto_Anterior'] = df_gold['Monto_Anterior'].fillna(0)
            
            # Calculate Variation: Current - Previous
            df_gold['Variacion_Mes_Anterior'] = df_gold['Monto'] - df_gold['Monto_Anterior']
            
            # Clean up temporary column
            df_gold = df_gold.drop(columns=['Monto_Anterior'])

        logging.info(f"Gold Layer generated with {len(df_gold)} rows.")

        # Export to Google Sheets
        output_sheet_name = 'Consolidacion'
        if not df_gold.empty:
            try:
                try:
                    worksheet = sh.worksheet(output_sheet_name)
                    logging.info(f"Clearing existing sheet '{output_sheet_name}'...")
                    worksheet.clear()
                except gspread.WorksheetNotFound:
                    logging.info(f"Creating sheet '{output_sheet_name}'...")
                    worksheet = sh.add_worksheet(title=output_sheet_name, rows=len(df_gold)+100, cols=len(df_gold.columns))

                df_export = df_gold.copy()
                for col in df_export.select_dtypes(include=['datetime64', 'datetimetz']).columns:
                    df_export[col] = df_export[col].dt.strftime('%Y-%m-%d')
                
                df_export = df_export.fillna('')
                data_to_write = [df_export.columns.tolist()] + df_export.values.tolist()
                worksheet.update(values=data_to_write, range_name='A1')
                logging.info(f"Successfully exported {len(df_export)} rows to '{output_sheet_name}'.")

            except Exception as e:
                logging.error(f"Error exporting to Google Sheets: {e}")
                raise e
        else:
            logging.warning("df_gold is empty. Nothing to export.")
            
    except Exception as e:
        logging.error(f"Critical error in main process: {e}", exc_info=True)
        raise e

if __name__ == "__main__":
    main()
