import streamlit as st
import requests
import os
import pandas as pd
from datetime import datetime

QIF_API_URL = os.environ.get("QIF_API_URL", "http://qif-agent:8000")

st.set_page_config(page_title="QIF Agent", page_icon="", layout="wide")

# Sidebar navigation
page = st.sidebar.selectbox("Choose a page", ["Chat", "Recurring Analysis", "Merchant Analysis", "Anomaly Detection", "Cash Flow Forecast", "Investment Portfolio", "Transfer Analysis", "Budget & Goals", "PDF Debug Viewer"])

if page == "Chat":
    st.title("Chat with My QIF Agent")
    st.markdown("""
        Ask questions about your finances! 
        The agent is trained on your QIF files and can answer queries about transactions.
        The table fields are:
        - **date**: The date of the transaction
        - **payee**: The entity you paid or received money from
        - **category**: The category of the transaction
        - **memo**: Additional notes about the transaction
        - **amount**: The amount of money involved in the transaction
        - **source_file**: The QIF file this transaction came from
        - **account_name**: The account name from the QIF file
        - **account_type**: The type of account (Bank, Credit Card, Investment, etc.)

        
        You can ask about specific transactions, totals, or trends in your finances.
        - For example, what the sum total for all of 2018 where the category like Dues?
        - List all transaction from 2018 where category like Util or like Electric
        """)
    
    if "history" not in st.session_state:
        st.session_state.history = []

    user_input = st.chat_input("Ask about your finances, table fields are date, payee, category, memo, amount, source_file, account_name, account_type.")

    if user_input:
        st.session_state.history.append({"role": "user", "content": user_input})
        # Call the QIF FastAPI agent
        try:
            resp = requests.post(f"{QIF_API_URL}/chat", json={"question": user_input}, timeout=60)
            if resp.status_code == 400:
                # Guardrail rejection or bad request
                err = resp.json().get("detail", "Your query was blocked by safety checks. Try rephrasing.")
                answer = f"Query blocked: {err}"
                st.session_state.history.append({"role": "assistant", "content": answer})
            else:
                data = resp.json()
                answer = data.get("answer", "No answer.")
                sql = data.get("sql", "")
                explanation = data.get("explanation", "")
                
                # Store the full response data for display
                st.session_state.history.append({
                    "role": "assistant", 
                    "content": answer,
                    "sql": sql,
                    "explanation": explanation
                })
        except Exception as e:
            answer = f"Error: {e}"
            st.session_state.history.append({"role": "assistant", "content": answer})

    for entry in st.session_state.history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            
            # Show SQL and explanation for assistant responses
            if entry["role"] == "assistant" and "sql" in entry and entry["sql"]:
                with st.expander("View SQL Query", expanded=False):
                    st.code(entry["sql"], language="sql")
                    if entry.get("explanation"):
                        st.markdown(f"**Explanation:** {entry['explanation']}")

elif page == "Recurring Analysis":
    st.title("Recurring Transaction Analysis")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Analyze Recurring Patterns", type="primary"):
            with st.spinner("Analyzing recurring patterns..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/analyze/recurring", timeout=120)
                    if resp.status_code == 200:
                        st.success("Analysis complete!")
                        st.rerun()
                    else:
                        st.error(f"Analysis failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display recurring patterns
    try:
        resp = requests.get(f"{QIF_API_URL}/recurring", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            patterns = data.get('patterns', [])
            projections = data.get('projections', {})
            
            if patterns:
                # Display projections
                st.subheader("Monthly Spending Projections")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Monthly", f"${projections.get('monthly_projection', 0):,.2f}")
                with col2:
                    st.metric("Weekly", f"${projections.get('weekly_projection', 0):,.2f}")
                with col3:
                    st.metric("Quarterly", f"${projections.get('quarterly_projection', 0):,.2f}")
                with col4:
                    st.metric("Yearly", f"${projections.get('yearly_projection', 0):,.2f}")
                
                # Display patterns table
                st.subheader("Detected Recurring Patterns")
                df = pd.DataFrame(patterns)
                
                # Format the dataframe for display
                display_df = df[['merchant_pattern', 'amount_avg', 'frequency_category', 
                                'confidence_score', 'transaction_count', 'next_expected']].copy()
                display_df.columns = ['Merchant', 'Avg Amount', 'Frequency', 'Confidence', 'Count', 'Next Expected']
                display_df['Avg Amount'] = display_df['Avg Amount'].apply(lambda x: f"${x:,.2f}")
                display_df['Confidence'] = display_df['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_df, use_container_width=True)
                
                # Show detailed view for selected pattern
                if len(patterns) > 0:
                    st.subheader("Pattern Details")
                    selected_idx = st.selectbox("Select a pattern to view details:", 
                                              range(len(patterns)),
                                              format_func=lambda x: f"{patterns[x]['merchant_pattern']} - {patterns[x]['frequency_category']}")
                    
                    if selected_idx is not None:
                        pattern = patterns[selected_idx]
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Merchant:** {pattern['merchant_pattern']}")
                            st.write(f"**Average Amount:** ${pattern['amount_avg']:,.2f}")
                            st.write(f"**Frequency:** {pattern['frequency_category']} (every {pattern['frequency_days']:.1f} days)")
                            st.write(f"**Confidence:** {pattern['confidence_score']:.1%}")
                            
                        with col2:
                            st.write(f"**Last Seen:** {pattern['last_seen']}")
                            st.write(f"**Next Expected:** {pattern['next_expected']}")
                            st.write(f"**Transaction Count:** {pattern['transaction_count']}")
                            st.write(f"**Category:** {pattern['category']}")
            else:
                st.info("No recurring patterns detected. Click 'Analyze Recurring Patterns' to run the analysis.")
                
        else:
            st.error(f"Failed to load recurring patterns: {resp.text}")
    except Exception as e:
        st.error(f"Error loading recurring patterns: {e}")

elif page == "Merchant Analysis":
    st.title("Merchant Analysis")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Normalize Merchants", type="primary"):
            with st.spinner("Normalizing merchant names..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/admin/normalize-merchants", timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success(f"Normalized {len(data.get('mappings', {}))} merchants!")
                        st.rerun()
                    else:
                        st.error(f"Normalization failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display merchant data
    try:
        resp = requests.get(f"{QIF_API_URL}/merchants", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            statistics = data.get('statistics', {})
            top_merchants = data.get('top_merchants', [])
            
            if statistics:
                # Display statistics
                st.subheader("Merchant Statistics")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Merchants", statistics.get('total_merchants', 0))
                with col2:
                    st.metric("Canonical Names", statistics.get('canonical_merchants', 0))
                with col3:
                    st.metric("Avg Transactions", f"{statistics.get('avg_transactions_per_merchant', 0):.1f}")
                with col4:
                    st.metric("Max Transactions", statistics.get('max_transactions', 0))
                
                # Display top merchants
                if top_merchants:
                    st.subheader("Top Merchants by Transaction Count")
                    df = pd.DataFrame(top_merchants)
                    display_df = df[['canonical_name', 'transaction_count', 'original_name']].copy()
                    display_df.columns = ['Canonical Name', 'Transaction Count', 'Original Name']
                    
                    st.dataframe(display_df, use_container_width=True)
                else:
                    st.info("No merchant data available. Click 'Normalize Merchants' to run the analysis.")
            else:
                st.info("No merchant statistics available. Click 'Normalize Merchants' to run the analysis.")
                
        else:
            st.error(f"Failed to load merchant data: {resp.text}")
    except Exception as e:
        st.error(f"Error loading merchant data: {e}")

elif page == "Anomaly Detection":
    st.title("Anomaly Detection")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Analyze Anomalies", type="primary"):
            with st.spinner("Analyzing anomalies..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/analyze/anomalies", timeout=120)
                    if resp.status_code == 200:
                        st.success("Anomaly analysis complete!")
                        st.rerun()
                    else:
                        st.error(f"Analysis failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display anomalies
    try:
        resp = requests.get(f"{QIF_API_URL}/anomalies", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            anomalies = data.get('anomalies', [])
            summary = data.get('summary', {})
            
            if anomalies:
                # Display summary
                if summary:
                    st.subheader("Anomaly Summary")
                    for anomaly_type, stats in summary.items():
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric(f"{anomaly_type.replace('_', ' ').title()} Count", stats['count'])
                        with col2:
                            st.metric("Avg Score", f"{stats['avg_score']:.2f}")
                        with col3:
                            st.metric("Max Score", f"{stats['max_score']:.2f}")
                
                # Display anomalies table
                st.subheader("Detected Anomalies")
                df = pd.DataFrame(anomalies)
                
                # Format the dataframe for display
                display_df = df[['date', 'payee', 'amount', 'anomaly_type', 'score', 'explanation']].copy()
                display_df.columns = ['Date', 'Merchant', 'Amount', 'Type', 'Score', 'Explanation']
                display_df['Amount'] = display_df['Amount'].apply(lambda x: f"${x:,.2f}")
                display_df['Score'] = display_df['Score'].apply(lambda x: f"{x:.2f}")
                
                st.dataframe(display_df, use_container_width=True)
                
                # Show detailed view for selected anomaly
                if len(anomalies) > 0:
                    st.subheader("Anomaly Details")
                    selected_idx = st.selectbox("Select an anomaly to view details:", 
                                              range(len(anomalies)),
                                              format_func=lambda x: f"{anomalies[x]['payee']} - {anomalies[x]['anomaly_type']} (Score: {anomalies[x]['score']:.2f})")
                    
                    if selected_idx is not None:
                        anomaly = anomalies[selected_idx]
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Date:** {anomaly['date']}")
                            st.write(f"**Merchant:** {anomaly['payee']}")
                            st.write(f"**Amount:** ${anomaly['amount']:,.2f}")
                            st.write(f"**Type:** {anomaly['anomaly_type']}")
                            
                        with col2:
                            st.write(f"**Score:** {anomaly['score']:.2f}")
                            st.write(f"**Category:** {anomaly['category']}")
                            st.write(f"**Account:** {anomaly['account_name']}")
                            st.write(f"**Explanation:** {anomaly['explanation']}")
            else:
                st.info("No anomalies detected. Click 'Analyze Anomalies' to run the analysis.")
                
        else:
            st.error(f"Failed to load anomalies: {resp.text}")
    except Exception as e:
        st.error(f"Error loading anomalies: {e}")

elif page == "Cash Flow Forecast":
    st.title("Cash Flow Forecast")
    
    # Forecast controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        forecast_days = st.selectbox("Forecast Period", [30, 60, 90], index=0)
    
    with col2:
        if st.button("Generate Forecast", type="primary"):
            st.rerun()
    
    with col3:
        show_trends = st.checkbox("Show Trends", value=True)
    
    # Get forecast data
    try:
        # Get overall forecast
        resp = requests.get(f"{QIF_API_URL}/forecast/{forecast_days}", timeout=30)
        if resp.status_code == 200:
            forecast = resp.json()
            
            # Display key metrics
            st.subheader("Forecast Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Current Balance", f"${forecast['current_balance']:,.2f}")
            with col2:
                st.metric("Projected Balance", f"${forecast['projected_balance']:,.2f}")
            with col3:
                st.metric("Projected Income", f"${forecast['projected_income']:,.2f}")
            with col4:
                st.metric("Projected Expenses", f"${forecast['projected_expenses']:,.2f}")
            
            # Safe to spend amount
            st.subheader("Safe to Spend")
            safe_amount = forecast['safe_to_spend']
            if safe_amount > 0:
                st.success(f"**${safe_amount:,.2f}** available for discretionary spending")
            else:
                st.warning(f"**${abs(safe_amount):,.2f}** projected shortfall - consider reducing expenses")
            
            # Upcoming bills
            if forecast['upcoming_bills']:
                st.subheader("Upcoming Bills")
                bills_df = pd.DataFrame(forecast['upcoming_bills'])
                display_bills = bills_df[['merchant', 'amount', 'due_date', 'frequency', 'confidence']].copy()
                display_bills.columns = ['Merchant', 'Amount', 'Due Date', 'Frequency', 'Confidence']
                display_bills['Amount'] = display_bills['Amount'].apply(lambda x: f"${x:,.2f}")
                display_bills['Confidence'] = display_bills['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_bills, use_container_width=True)
            
            # Daily forecast chart
            if forecast['daily_forecast']:
                st.subheader("Daily Balance Projection")
                daily_df = pd.DataFrame(forecast['daily_forecast'])
                daily_df['date'] = pd.to_datetime(daily_df['date'])
                
                # Create a simple line chart
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_df['date'], daily_df['projected_balance'], linewidth=2)
                ax.set_title('Projected Balance Over Time')
                ax.set_xlabel('Date')
                ax.set_ylabel('Balance ($)')
                ax.grid(True, alpha=0.3)
                
                # Format y-axis as currency
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
                
                # Rotate x-axis labels
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
            
            # Spending trends
            if show_trends:
                try:
                    trends_resp = requests.get(f"{QIF_API_URL}/forecast/trends", timeout=30)
                    if trends_resp.status_code == 200:
                        trends = trends_resp.json()
                        
                        if trends['trends']:
                            st.subheader("Historical Spending Trends")
                            trends_df = pd.DataFrame(trends['trends'])
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Avg Monthly Income", f"${trends['avg_monthly_income']:,.2f}")
                            with col2:
                                st.metric("Avg Monthly Expenses", f"${trends['avg_monthly_expenses']:,.2f}")
                            
                            # Display trends table
                            display_trends = trends_df[['month', 'income', 'expenses', 'transaction_count']].copy()
                            display_trends.columns = ['Month', 'Income', 'Expenses', 'Transactions']
                            display_trends['Income'] = display_trends['Income'].apply(lambda x: f"${x:,.2f}")
                            display_trends['Expenses'] = display_trends['Expenses'].apply(lambda x: f"${x:,.2f}")
                            
                            st.dataframe(display_trends, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not load spending trends: {e}")
        else:
            st.error(f"Failed to load forecast: {resp.text}")
    except Exception as e:
        st.error(f"Error loading forecast: {e}")

elif page == "Investment Portfolio":
    st.title("Investment Portfolio")
    
    # Portfolio controls
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Parse Investments", type="primary"):
            with st.spinner("Parsing investment data..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/admin/parse-investments", timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('status') == 'success':
                            st.success(f"Parsed {data.get('transactions_count', 0)} investment transactions!")
                        else:
                            st.warning(f"Parsing result: {data.get('message', 'Unknown status')}")
                        st.rerun()
                    else:
                        st.error(f"Parsing failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get portfolio data
    try:
        # Portfolio summary
        resp = requests.get(f"{QIF_API_URL}/investments/portfolio", timeout=30)
        if resp.status_code == 200:
            portfolio = resp.json()
            
            if portfolio.get('holdings'):
                # Display portfolio metrics
                st.subheader("Portfolio Summary")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Value", f"${portfolio['total_value']:,.2f}")
                with col2:
                    st.metric("Total Invested", f"${portfolio['total_invested']:,.2f}")
                with col3:
                    st.metric("Gain/Loss", f"${portfolio['total_gain_loss']:,.2f}")
                with col4:
                    st.metric("Return %", f"{portfolio['overall_return']:.2f}%")
                
                # Holdings table
                st.subheader("Current Holdings")
                holdings_df = pd.DataFrame(portfolio['holdings'])
                display_holdings = holdings_df[['security', 'total_quantity', 'avg_price', 'current_value', 'unrealized_gain_loss', 'return_percentage']].copy()
                display_holdings.columns = ['Security', 'Quantity', 'Avg Price', 'Current Value', 'Gain/Loss', 'Return %']
                display_holdings['Current Value'] = display_holdings['Current Value'].apply(lambda x: f"${x:,.2f}")
                display_holdings['Gain/Loss'] = display_holdings['Gain/Loss'].apply(lambda x: f"${x:,.2f}")
                display_holdings['Return %'] = display_holdings['Return %'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(display_holdings, use_container_width=True)
                
                # Asset allocation
                try:
                    allocation_resp = requests.get(f"{QIF_API_URL}/investments/allocation", timeout=30)
                    if allocation_resp.status_code == 200:
                        allocation = allocation_resp.json()
                        
                        if allocation.get('allocation'):
                            st.subheader("Asset Allocation")
                            allocation_df = pd.DataFrame(allocation['allocation'])
                            
                            # Create pie chart
                            import matplotlib.pyplot as plt
                            fig, ax = plt.subplots(figsize=(10, 8))
                            
                            # Filter out small allocations for cleaner chart
                            min_allocation = 2.0  # 2% minimum
                            filtered_allocation = allocation_df[allocation_df['allocation_percentage'] >= min_allocation]
                            others = allocation_df[allocation_df['allocation_percentage'] < min_allocation]['allocation_percentage'].sum()
                            
                            if others > 0:
                                filtered_allocation = pd.concat([filtered_allocation, pd.DataFrame([{
                                    'security': 'Others',
                                    'allocation_percentage': others
                                }])])
                            
                            ax.pie(filtered_allocation['allocation_percentage'], 
                                  labels=filtered_allocation['security'],
                                  autopct='%1.1f%%',
                                  startangle=90)
                            ax.set_title('Asset Allocation')
                            st.pyplot(fig)
                except Exception as e:
                    st.warning(f"Could not load asset allocation: {e}")
            else:
                st.info("No investment data available. Click 'Parse Investments' to load investment data from QIF files.")
        else:
            st.error(f"Failed to load portfolio: {resp.text}")
    except Exception as e:
        st.error(f"Error loading portfolio: {e}")
    
    # Performance analysis
    try:
        perf_resp = requests.get(f"{QIF_API_URL}/investments/performance", timeout=30)
        if perf_resp.status_code == 200:
            performance = perf_resp.json()
            
            if performance.get('monthly_performance'):
                st.subheader("Monthly Performance")
                perf_df = pd.DataFrame(performance['monthly_performance'])
                display_perf = perf_df[['month', 'total_amount', 'transaction_count']].copy()
                display_perf.columns = ['Month', 'Total Amount', 'Transactions']
                display_perf['Total Amount'] = display_perf['Total Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_perf, use_container_width=True)
            
            if performance.get('action_breakdown'):
                st.subheader("Transaction Types")
                action_df = pd.DataFrame(performance['action_breakdown'])
                display_action = action_df[['action', 'total_amount', 'transaction_count']].copy()
                display_action.columns = ['Action', 'Total Amount', 'Count']
                display_action['Total Amount'] = display_action['Total Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_action, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load performance data: {e}")
    
    # Recent transactions
    try:
        trans_resp = requests.get(f"{QIF_API_URL}/investments/transactions", timeout=30)
        if trans_resp.status_code == 200:
            transactions = trans_resp.json().get('transactions', [])
            
            if transactions:
                st.subheader("Recent Transactions")
                trans_df = pd.DataFrame(transactions)
                display_trans = trans_df[['date', 'security', 'action', 'quantity', 'price', 'amount']].copy()
                display_trans.columns = ['Date', 'Security', 'Action', 'Quantity', 'Price', 'Amount']
                display_trans['Price'] = display_trans['Price'].apply(lambda x: f"${x:,.2f}")
                display_trans['Amount'] = display_trans['Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_trans, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load transaction history: {e}")

elif page == "Transfer Analysis":
    st.title("Transfer Analysis")
    
    # Transfer controls
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Detect Transfers", type="primary"):
            with st.spinner("Detecting transfers..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/admin/detect-transfers", timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success(f"Detected {len(data.get('transfers', []))} transfers!")
                        st.rerun()
                    else:
                        st.error(f"Transfer detection failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get transfer data
    try:
        resp = requests.get(f"{QIF_API_URL}/transfers", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            transfers = data.get('transfers', [])
            summary = data.get('summary', {})
            
            if transfers:
                # Display summary
                st.subheader("Transfer Summary")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Transfers", summary.get('total_transfers', 0))
                with col2:
                    st.metric("Total Amount", f"${summary.get('total_transfer_amount', 0):,.2f}")
                with col3:
                    st.metric("Avg Confidence", f"{summary.get('avg_confidence', 0):.1%}")
                with col4:
                    st.metric("Unique Accounts", summary.get('unique_from_accounts', 0))
                
                # Display transfers table
                st.subheader("Detected Transfers")
                transfers_df = pd.DataFrame(transfers)
                display_transfers = transfers_df[['from_account', 'to_account', 'amount', 'transfer_date', 'confidence_score']].copy()
                display_transfers.columns = ['From Account', 'To Account', 'Amount', 'Date', 'Confidence']
                display_transfers['Amount'] = display_transfers['Amount'].apply(lambda x: f"${x:,.2f}")
                display_transfers['Confidence'] = display_transfers['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_transfers, use_container_width=True)
                
                # Net cash flow analysis
                st.subheader("Net Cash Flow Analysis")
                try:
                    cash_flow_resp = requests.get(f"{QIF_API_URL}/transfers/cash-flow", timeout=30)
                    if cash_flow_resp.status_code == 200:
                        cash_flow = cash_flow_resp.json()
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total Income", f"${cash_flow.get('total_income', 0):,.2f}")
                        with col2:
                            st.metric("Total Expenses", f"${cash_flow.get('total_expenses', 0):,.2f}")
                        with col3:
                            st.metric("Net Cash Flow", f"${cash_flow.get('net_cash_flow', 0):,.2f}")
                        with col4:
                            st.metric("Transactions", cash_flow.get('transaction_count', 0))
                except Exception as e:
                    st.warning(f"Could not load cash flow data: {e}")
            else:
                st.info("No transfers detected. Click 'Detect Transfers' to analyze account transfers.")
        else:
            st.error(f"Failed to load transfers: {resp.text}")
    except Exception as e:
        st.error(f"Error loading transfers: {e}")

elif page == "Budget & Goals":
    st.title("Budget & Goals")
    
    # Create tabs for budgets and goals
    tab1, tab2 = st.tabs(["Budgets", "Goals"])
    
    with tab1:
        st.subheader("Budget Management")
        
        # Budget controls
        col1, col2 = st.columns([3, 1])
        
        with col2:
            if st.button("Get AI Suggestions", type="primary"):
                with st.spinner("Analyzing spending patterns..."):
                    try:
                        resp = requests.get(f"{QIF_API_URL}/budgets/suggestions", timeout=60)
                        if resp.status_code == 200:
                            suggestions = resp.json().get('suggestions', [])
                            st.session_state['budget_suggestions'] = suggestions
                            st.success(f"Generated {len(suggestions)} budget suggestions!")
                        else:
                            st.error(f"Failed to get suggestions: {resp.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        # Display budget suggestions
        if 'budget_suggestions' in st.session_state:
            suggestions = st.session_state['budget_suggestions']
            if suggestions:
                st.subheader("AI-Powered Budget Suggestions")
                suggestions_df = pd.DataFrame(suggestions)
                display_suggestions = suggestions_df[['category', 'suggested_amount', 'historical_average', 'confidence']].copy()
                display_suggestions.columns = ['Category', 'Suggested Amount', 'Historical Average', 'Confidence']
                display_suggestions['Suggested Amount'] = display_suggestions['Suggested Amount'].apply(lambda x: f"${x:,.2f}")
                display_suggestions['Historical Average'] = display_suggestions['Historical Average'].apply(lambda x: f"${x:,.2f}")
                display_suggestions['Confidence'] = display_suggestions['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_suggestions, use_container_width=True)
        
        # Create new budget form
        with st.expander("Create New Budget", expanded=False):
            with st.form("create_budget"):
                category = st.text_input("Category")
                amount = st.number_input("Amount", min_value=0.0, step=0.01)
                period = st.selectbox("Period", ["monthly", "weekly", "yearly"])
                
                if st.form_submit_button("Create Budget"):
                    if category and amount > 0:
                        try:
                            resp = requests.post(f"{QIF_API_URL}/budgets", 
                                               json={"category": category, "amount": amount, "period": period})
                            if resp.status_code == 200:
                                st.success("Budget created successfully!")
                                st.rerun()
                            else:
                                st.error(f"Failed to create budget: {resp.text}")
                        except Exception as e:
                            st.error(f"Error: {e}")
        
        # Display budgets and progress
        try:
            resp = requests.get(f"{QIF_API_URL}/budgets", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                budgets = data.get('budgets', [])
                progress = data.get('progress', [])
                summary = data.get('summary', {})
                
                if budgets:
                    # Budget summary
                    st.subheader("Budget Summary")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Budgets", summary.get('total_budgets', 0))
                    with col2:
                        st.metric("Total Amount", f"${summary.get('total_budget_amount', 0):,.2f}")
                    with col3:
                        st.metric("Goal Completion", f"{summary.get('goal_completion_rate', 0):.1f}%")
                    
                    # Budget progress
                    st.subheader("Budget Progress")
                    progress_df = pd.DataFrame(progress)
                    if not progress_df.empty:
                        display_progress = progress_df[['category', 'budget_amount', 'actual_spent', 'progress_percentage', 'over_budget']].copy()
                        display_progress.columns = ['Category', 'Budget', 'Spent', 'Progress %', 'Over Budget']
                        display_progress['Budget'] = display_progress['Budget'].apply(lambda x: f"${x:,.2f}")
                        display_progress['Spent'] = display_progress['Spent'].apply(lambda x: f"${x:,.2f}")
                        display_progress['Progress %'] = display_progress['Progress %'].apply(lambda x: f"{x:.1f}%")
                        display_progress['Over Budget'] = display_progress['Over Budget'].apply(lambda x: "Yes" if x else "No")
                        
                        st.dataframe(display_progress, use_container_width=True)
                else:
                    st.info("No budgets created yet. Use the form above to create your first budget.")
        except Exception as e:
            st.error(f"Error loading budgets: {e}")
    
    with tab2:
        st.subheader("Financial Goals")
        
        # Create new goal form
        with st.expander("Create New Goal", expanded=False):
            with st.form("create_goal"):
                name = st.text_input("Goal Name")
                target_amount = st.number_input("Target Amount", min_value=0.0, step=0.01)
                deadline = st.date_input("Deadline (optional)")
                category = st.text_input("Category (optional)")
                
                if st.form_submit_button("Create Goal"):
                    if name and target_amount > 0:
                        try:
                            goal_data = {
                                "name": name,
                                "target_amount": target_amount,
                                "category": category if category else None
                            }
                            if deadline:
                                goal_data["deadline"] = deadline.isoformat()
                            
                            resp = requests.post(f"{QIF_API_URL}/goals", json=goal_data)
                            if resp.status_code == 200:
                                st.success("Goal created successfully!")
                                st.rerun()
                            else:
                                st.error(f"Failed to create goal: {resp.text}")
                        except Exception as e:
                            st.error(f"Error: {e}")
        
        # Display goals and progress
        try:
            resp = requests.get(f"{QIF_API_URL}/goals", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                goals = data.get('goals', [])
                progress = data.get('progress', [])
                summary = data.get('summary', {})
                
                if goals:
                    # Goals summary
                    st.subheader("Goals Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Goals", summary.get('total_goals', 0))
                    with col2:
                        st.metric("Target Amount", f"${summary.get('total_goal_amount', 0):,.2f}")
                    with col3:
                        st.metric("Current Progress", f"${summary.get('total_goal_progress', 0):,.2f}")
                    with col4:
                        st.metric("Completion Rate", f"{summary.get('goal_completion_rate', 0):.1f}%")
                    
                    # Goals progress
                    st.subheader("Goals Progress")
                    progress_df = pd.DataFrame(progress)
                    if not progress_df.empty:
                        display_progress = progress_df[['name', 'target_amount', 'current_amount', 'progress_percentage', 'is_complete']].copy()
                        display_progress.columns = ['Goal', 'Target', 'Current', 'Progress %', 'Complete']
                        display_progress['Target'] = display_progress['Target'].apply(lambda x: f"${x:,.2f}")
                        display_progress['Current'] = display_progress['Current'].apply(lambda x: f"${x:,.2f}")
                        display_progress['Progress %'] = display_progress['Progress %'].apply(lambda x: f"{x:.1f}%")
                        display_progress['Complete'] = display_progress['Complete'].apply(lambda x: "Yes" if x else "No")
                        
                        st.dataframe(display_progress, use_container_width=True)
                else:
                    st.info("No goals created yet. Use the form above to create your first goal.")
        except Exception as e:
            st.error(f"Error loading goals: {e}")

elif page == "PDF Debug Viewer":
    st.title("PDF Debug Viewer")
    st.markdown("""
    This tool helps you debug PDF extraction before ingestion. 
    Upload a PDF or select from existing fund documents to see what text is extracted.
    """)
    
    # Import required modules for PDF processing
    try:
        import pdfplumber
        import os
        import re
        from pathlib import Path
        
        st.success("PDF processing modules loaded successfully!")
        
        # Simplified PDF processing functions for UI
        def extract_text_pages(pdf_path):
            """Extract text from all pages of a PDF"""
            pages = []
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            pages.append(text)
            except Exception as e:
                st.error(f"Error extracting text: {e}")
            return pages
        
        def detect_fund_name(pages):
            """Simple fund name detection"""
            if not pages:
                return None
            
            # Look for common fund name patterns
            text = " ".join(pages[:2])  # Check first 2 pages
            patterns = [
                r"fund\s+name[:\s]+([A-Za-z\s&,.-]+)",
                r"([A-Za-z\s&,.-]+)\s+fund",
                r"([A-Za-z\s&,.-]+)\s+partnership"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            return "Unknown Fund"
        
        def detect_as_of_date(pages):
            """Simple date detection"""
            if not pages:
                return None
            
            text = " ".join(pages[:2])  # Check first 2 pages
            date_patterns = [
                r"as\s+of\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})"
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)
            return None
        
        def classify_doc_type(pages):
            """Simple document type classification"""
            if not pages:
                return "Unknown"
            
            text = " ".join(pages[:2]).lower()
            
            if any(keyword in text for keyword in ["capital call", "drawdown"]):
                return "Capital Call"
            elif any(keyword in text for keyword in ["distribution", "capital distribution"]):
                return "Distribution"
            elif any(keyword in text for keyword in ["quarterly", "annual", "report"]):
                return "Report"
            else:
                return "Other"
        
        def parse_metrics(pages):
            """Simple metrics parsing"""
            if not pages:
                return {}
            
            text = " ".join(pages)
            metrics = {}
            
            # Look for NAV
            nav_match = re.search(r"nav[:\s]*\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
            if nav_match:
                try:
                    metrics["nav"] = float(nav_match.group(1).replace(",", ""))
                except:
                    pass
            
            # Look for IRR
            irr_match = re.search(r"irr[:\s]*([\d,]+\.?\d*)%?", text, re.IGNORECASE)
            if irr_match:
                try:
                    metrics["irr"] = float(irr_match.group(1).replace(",", ""))
                except:
                    pass
            
            return metrics
        
        def parse_cash_flows(pages):
            """Simple cash flow parsing"""
            if not pages:
                return []
            
            text = " ".join(pages)
            cash_flows = []
            
            # Look for cash flow amounts
            amount_pattern = r"\$?([\d,]+\.?\d*)\s*(?:million|m|billion|b)?"
            amounts = re.findall(amount_pattern, text, re.IGNORECASE)
            
            for amount in amounts[:10]:  # Limit to first 10 matches
                try:
                    value = float(amount.replace(",", ""))
                    cash_flows.append(value)
                except:
                    pass
            
            return cash_flows
        
        # File selection
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Upload New PDF")
            uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'])
            
        with col2:
            st.subheader("Select Existing PDF")
            # Try multiple possible paths for the PDF directory
            # Get the directory where this Streamlit file is located
            streamlit_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(streamlit_dir)  # Go up one level from ui/ to project root
            
            possible_paths = [
                os.getenv('FUND_PDF_DIR', 'docs/fund_pdfs'),
                '/docs/fund_pdfs',  # Docker mount path
                'docs/fund_pdfs',
                '../docs/fund_pdfs',
                './docs/fund_pdfs',
                os.path.join(os.getcwd(), 'docs', 'fund_pdfs'),
                os.path.join(project_root, 'docs', 'fund_pdfs'),
                os.path.join(streamlit_dir, '..', 'docs', 'fund_pdfs'),
                os.path.join(os.path.dirname(os.getcwd()), 'docs', 'fund_pdfs')
            ]
            
            pdf_dir = None
            for path in possible_paths:
                if os.path.exists(path):
                    pdf_dir = path
                    break
            
            # If no directory found, try to create the default one
            if not pdf_dir:
                default_path = 'docs/fund_pdfs'
                try:
                    os.makedirs(default_path, exist_ok=True)
                    if os.path.exists(default_path):
                        pdf_dir = default_path
                        st.info(f"Created PDF directory: {pdf_dir}")
                except Exception as e:
                    st.warning(f"Could not create PDF directory: {e}")
            
            if pdf_dir:
                pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
                if pdf_files:
                    selected_file = st.selectbox("Choose from existing PDFs", [""] + pdf_files)
                    st.success(f"✅ Found {len(pdf_files)} PDF files in: {pdf_dir}")
                    st.info(f"Available PDFs: {', '.join(pdf_files)}")
                else:
                    st.info(f"No PDF files found in {pdf_dir}")
                    selected_file = ""
            else:
                st.warning(f"PDF directory not found. Tried paths: {possible_paths}")
                st.info("You can still upload a PDF using the upload widget on the left.")
                st.info(f"Current working directory: {os.getcwd()}")
                st.info(f"Environment FUND_PDF_DIR: {os.getenv('FUND_PDF_DIR', 'Not set')}")
                selected_file = ""
        
        # Process selected file
        pdf_path = None
        if uploaded_file:
            pdf_path = uploaded_file
            filename = uploaded_file.name
        elif selected_file:
            pdf_path = os.path.join(pdf_dir, selected_file)
            filename = selected_file
        else:
            st.info("Please upload a PDF or select an existing one to begin analysis.")
        
        if pdf_path:
            st.divider()
            st.subheader(f"Analysis: {filename}")
            
            try:
                # Extract text using pdfplumber
                if uploaded_file:
                    # For uploaded files, save temporarily
                    temp_path = f"/tmp/{filename}"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    pages = extract_text_pages(temp_path)
                    os.remove(temp_path)
                else:
                    pages = extract_text_pages(pdf_path)
                
                # Display metadata
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Pages Extracted", len(pages))
                with col2:
                    total_chars = sum(len(page) for page in pages)
                    st.metric("Total Characters", f"{total_chars:,}")
                with col3:
                    avg_chars = total_chars // len(pages) if pages else 0
                    st.metric("Avg Chars/Page", f"{avg_chars:,}")
                
                # Run pattern detection
                st.subheader("Pattern Detection Results")
                
                fund_name = detect_fund_name(pages)
                as_of_date = detect_as_of_date(pages)
                doc_type = classify_doc_type(pages)
                metrics = parse_metrics(pages)
                cash_flows = parse_cash_flows(pages)
                
                # Calculate confidence (simplified version)
                confidence = 0.6
                if metrics.get("nav") is not None or metrics.get("irr_net") is not None:
                    confidence += 0.2
                if as_of_date:
                    confidence += 0.1
                confidence = min(confidence, 0.95)
                
                # Display results
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Fund Name:**", fund_name)
                    st.write("**As of Date:**", as_of_date or "Not detected")
                    st.write("**Document Type:**", doc_type)
                    st.write("**Confidence Score:**", f"{confidence:.2f}")
                
                with col2:
                    st.write("**Metrics Found:**")
                    for key, value in metrics.items():
                        if value is not None:
                            st.write(f"- {key}: {value}")
                        else:
                            st.write(f"- {key}: Not found")
                    
                    st.write(f"**Cash Flows:** {len(cash_flows)} detected")
                
                # Show extracted text
                st.subheader("Extracted Text by Page")
                
                for i, page_text in enumerate(pages):
                    with st.expander(f"Page {i+1} ({len(page_text)} characters)"):
                        if page_text.strip():
                            st.text(page_text[:2000] + "..." if len(page_text) > 2000 else page_text)
                        else:
                            st.warning("No text extracted from this page")
                
                # Show what would be sent to LLM
                st.subheader("LLM Input Preview")
                llm_text = "\n".join(pages[:3])  # First 3 pages
                st.text_area("Text that would be sent to LLM:", llm_text[:3000] + "..." if len(llm_text) > 3000 else llm_text, height=200)
                
                # Test LLM extraction button
                if st.button("Test LLM Extraction", type="primary"):
                    st.subheader("LLM Extraction Results")
                    
                    with st.spinner("Calling LLM to extract fund data..."):
                        try:
                            # Call the API endpoint for LLM extraction
                            api_url = f"{QIF_API_URL}/admin/extract-llm"
                            response = requests.post(api_url, json={"pages": pages}, timeout=120)
                            
                            if response.status_code != 200:
                                st.error(f"API call failed: {response.status_code} - {response.text}")
                            else:
                                api_result = response.json()
                                if api_result.get("status") != "ok":
                                    st.error(f"LLM extraction failed: {api_result}")
                                else:
                                    llm_result = api_result.get("result", {})
                                    
                                    # Get LLM config for display
                                    llm_provider = os.getenv('LLM_PROVIDER', 'lmstudio')
                                    llm_model = os.getenv('LLM_MODEL', 'phi4-mini:3.8b')
                                    st.info(f"Using LLM Provider: **{llm_provider}** with model **{llm_model}**")
                                    
                                    # Display results
                                    if llm_result.get("extraction_method") == "llm_failed":
                                        st.error(f"LLM extraction failed: {llm_result.get('error', 'Unknown error')}")
                                    else:
                                        st.success("LLM extraction successful!")
                                        
                                        # Comparison table
                                        col1, col2 = st.columns(2)
                                        
                                        with col1:
                                            st.write("**Pattern Extraction**")
                                            st.write(f"Fund Name: {fund_name}")
                                            st.write(f"As of Date: {as_of_date or 'Not detected'}")
                                            st.write(f"Doc Type: {doc_type}")
                                            st.write(f"Confidence: {confidence:.2f}")
                                            st.write("**Metrics:**")
                                            for key, value in metrics.items():
                                                if value is not None:
                                                    st.write(f"- {key}: {value}")
                                        
                                        with col2:
                                            st.write("**LLM Extraction**")
                                            st.write(f"Fund Name: {llm_result.get('fund_name', 'N/A')}")
                                            st.write(f"As of Date: {llm_result.get('as_of_date') or 'Not detected'}")
                                            st.write(f"Doc Type: {llm_result.get('doc_type', 'N/A')}")
                                            st.write(f"Confidence: {llm_result.get('confidence', 0.0):.2f}")
                                            st.write("**Metrics:**")
                                            llm_metrics = llm_result.get('metrics', {})
                                            for key, value in llm_metrics.items():
                                                if value is not None:
                                                    st.write(f"- {key}: {value}")
                                        
                                        # Show comprehensive LLM extraction
                                        comprehensive_data = llm_result.get('comprehensive_data', {})
                                        if comprehensive_data:
                                            st.subheader("🔍 Comprehensive LLM Extraction Results")
                                            
                                            # Fund Information
                                            with st.expander("📊 Fund Information", expanded=True):
                                                col1, col2 = st.columns(2)
                                                with col1:
                                                    st.write(f"**Fund Type:** {comprehensive_data.get('fund_type', 'N/A')}")
                                                    st.write(f"**Fund Manager:** {comprehensive_data.get('fund_manager', 'N/A')}")
                                                    st.write(f"**Vintage Year:** {comprehensive_data.get('vintage_year', 'N/A')}")
                                                    st.write(f"**Strategy:** {comprehensive_data.get('strategy', 'N/A')}")
                                                with col2:
                                                    st.write(f"**Total Assets:** {comprehensive_data.get('total_assets', 'N/A')}")
                                                    st.write(f"**Expense Ratio:** {comprehensive_data.get('expense_ratio', 'N/A')}")
                                                    st.write(f"**Min Investment:** {comprehensive_data.get('minimum_investment', 'N/A')}")
                                            
                                            # Performance Metrics
                                            perf_metrics = comprehensive_data.get('performance_metrics', {})
                                            if any(perf_metrics.values()):
                                                with st.expander("📈 Performance Metrics"):
                                                    col1, col2, col3 = st.columns(3)
                                                    with col1:
                                                        st.write("**Returns:**")
                                                        for key in ['irr_net', 'irr_gross', 'alpha']:
                                                            if perf_metrics.get(key):
                                                                st.write(f"- {key}: {perf_metrics[key]}")
                                                    with col2:
                                                        st.write("**Multiples:**")
                                                        for key in ['tvpi', 'dpi', 'rvpi', 'pme']:
                                                            if perf_metrics.get(key):
                                                                st.write(f"- {key}: {perf_metrics[key]}")
                                                    with col3:
                                                        st.write("**Risk:**")
                                                        for key in ['volatility', 'max_drawdown', 'tracking_error']:
                                                            if perf_metrics.get(key):
                                                                st.write(f"- {key}: {perf_metrics[key]}")
                                            
                                            # Asset Allocation
                                            asset_alloc = comprehensive_data.get('asset_allocation', {})
                                            if any(asset_alloc.values()):
                                                with st.expander("🏦 Asset Allocation"):
                                                    for key, value in asset_alloc.items():
                                                        if value:
                                                            st.write(f"- {key.replace('_', ' ').title()}: {value}")
                                            
                                            # Fees
                                            fees = comprehensive_data.get('fees', {})
                                            if any(fees.values()):
                                                with st.expander("💰 Fees"):
                                                    for key, value in fees.items():
                                                        if value:
                                                            st.write(f"- {key.replace('_', ' ').title()}: {value}")
                                            
                                            # Ratings
                                            ratings = comprehensive_data.get('ratings', {})
                                            if any(ratings.values()):
                                                with st.expander("⭐ Ratings"):
                                                    for key, value in ratings.items():
                                                        if value:
                                                            st.write(f"- {key.replace('_', ' ').title()}: {value}")
                                            
                                            # Risk Metrics
                                            risk_metrics = comprehensive_data.get('risk_metrics', {})
                                            if any(risk_metrics.values()):
                                                with st.expander("⚠️ Risk Metrics"):
                                                    for key, value in risk_metrics.items():
                                                        if value:
                                                            st.write(f"- {key.replace('_', ' ').title()}: {value}")
                                            
                                            # Additional Info
                                            additional = comprehensive_data.get('additional_info', {})
                                            if any(additional.values()):
                                                with st.expander("ℹ️ Additional Information"):
                                                    for key, value in additional.items():
                                                        if value:
                                                            st.write(f"- {key.replace('_', ' ').title()}: {value}")
                                        
                                        # Show cash flows if found
                                        llm_flows = llm_result.get('cash_flows', [])
                                        if llm_flows:
                                            st.write("**LLM Detected Cash Flows:**")
                                            for flow in llm_flows:
                                                st.write(f"- {flow[0]}: ${flow[1]:,.2f} ({flow[2]}) - {flow[3]}")
                                        
                                        # Winner determination
                                        st.divider()
                                        pattern_conf = confidence
                                        llm_conf = llm_result.get('confidence', 0.0)
                                        
                                        if llm_conf > pattern_conf:
                                            st.success(f"🎯 LLM extraction has higher confidence ({llm_conf:.2f} vs {pattern_conf:.2f}). Recommend using LLM results.")
                                        else:
                                            st.info(f"📊 Pattern extraction has higher confidence ({pattern_conf:.2f} vs {llm_conf:.2f}). Recommend using pattern results.")
                        
                        except Exception as e:
                            st.error(f"Error during LLM extraction: {e}")
                            st.exception(e)
                
            except Exception as e:
                st.error(f"Error processing PDF: {e}")
                st.exception(e)
        
    except ImportError as e:
        st.error(f"Missing required modules: {e}")
        st.info("Make sure pdfplumber is installed and the app directory is accessible.")
    except Exception as e:
        st.error(f"Error loading PDF processing modules: {e}")
        st.exception(e)
