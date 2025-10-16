// Sample Financial Data for Dashboard Mockups

const sampleData = {
  // KPI Metrics
  kpis: {
    netWorth: {
      value: 125430.50,
      change: 8.2,
      trend: 'positive',
      label: 'Net Worth'
    },
    monthlyCashFlow: {
      value: 2840.75,
      change: -2.1,
      trend: 'negative',
      label: 'Monthly Cash Flow'
    },
    budgetUtilization: {
      value: 78.5,
      change: 5.3,
      trend: 'positive',
      label: 'Budget Utilization %'
    },
    investmentReturns: {
      value: 12.4,
      change: 3.2,
      trend: 'positive',
      label: 'Investment Returns %'
    }
  },

  // Spending Categories
  spendingCategories: [
    { name: 'Housing', amount: 2400, percentage: 35.2, color: '#42a5f5' },
    { name: 'Food & Dining', amount: 1200, percentage: 17.6, color: '#66bb6a' },
    { name: 'Transportation', amount: 800, percentage: 11.7, color: '#ffa726' },
    { name: 'Entertainment', amount: 600, percentage: 8.8, color: '#ef5350' },
    { name: 'Healthcare', amount: 450, percentage: 6.6, color: '#ab47bc' },
    { name: 'Shopping', amount: 400, percentage: 5.9, color: '#26a69a' },
    { name: 'Utilities', amount: 350, percentage: 5.1, color: '#ff7043' },
    { name: 'Other', amount: 620, percentage: 9.1, color: '#78909c' }
  ],

  // Cash Flow Forecast (30 days)
  cashFlowForecast: [
    { date: '2024-01-01', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-02', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-03', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-04', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-05', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-06', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-07', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-08', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-09', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-10', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-11', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-12', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-13', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-14', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-15', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-16', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-17', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-18', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-19', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-20', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-21', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-22', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-23', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-24', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-25', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-26', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-27', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-28', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-29', balance: 125430.50, income: 0, expenses: 0 },
    { date: '2024-01-30', balance: 125430.50, income: 0, expenses: 0 }
  ],

  // Recent Transactions
  recentTransactions: [
    {
      id: 1,
      date: '2024-01-15',
      payee: 'Amazon',
      category: 'Shopping',
      amount: -89.99,
      account: 'Chase Credit Card'
    },
    {
      id: 2,
      date: '2024-01-14',
      payee: 'Shell Gas Station',
      category: 'Transportation',
      amount: -45.20,
      account: 'Chase Credit Card'
    },
    {
      id: 3,
      date: '2024-01-14',
      payee: 'Salary Deposit',
      category: 'Income',
      amount: 4500.00,
      account: 'Chase Checking'
    },
    {
      id: 4,
      date: '2024-01-13',
      payee: 'Netflix',
      category: 'Entertainment',
      amount: -15.99,
      account: 'Chase Credit Card'
    },
    {
      id: 5,
      date: '2024-01-12',
      payee: 'Whole Foods',
      category: 'Food & Dining',
      amount: -127.45,
      account: 'Chase Credit Card'
    },
    {
      id: 6,
      date: '2024-01-11',
      payee: 'Rent Payment',
      category: 'Housing',
      amount: -1800.00,
      account: 'Chase Checking'
    },
    {
      id: 7,
      date: '2024-01-10',
      payee: 'Electric Bill',
      category: 'Utilities',
      amount: -125.30,
      account: 'Chase Checking'
    },
    {
      id: 8,
      date: '2024-01-09',
      payee: 'Starbucks',
      category: 'Food & Dining',
      amount: -4.75,
      account: 'Chase Credit Card'
    }
  ],

  // Recurring Patterns
  recurringPatterns: [
    {
      merchant: 'Netflix',
      amount: 15.99,
      frequency: 'Monthly',
      nextExpected: '2024-02-13',
      confidence: 0.95
    },
    {
      merchant: 'Rent Payment',
      amount: 1800.00,
      frequency: 'Monthly',
      nextExpected: '2024-02-11',
      confidence: 1.0
    },
    {
      merchant: 'Electric Bill',
      amount: 125.30,
      frequency: 'Monthly',
      nextExpected: '2024-02-10',
      confidence: 0.88
    },
    {
      merchant: 'Salary Deposit',
      amount: 4500.00,
      frequency: 'Monthly',
      nextExpected: '2024-02-14',
      confidence: 1.0
    }
  ],

  // Investment Portfolio
  portfolio: {
    totalValue: 45620.50,
    totalInvested: 42000.00,
    totalGainLoss: 3620.50,
    overallReturn: 8.62,
    holdings: [
      {
        security: 'AAPL',
        quantity: 25,
        avgPrice: 150.00,
        currentPrice: 185.50,
        currentValue: 4637.50,
        gainLoss: 887.50,
        returnPercentage: 23.67
      },
      {
        security: 'MSFT',
        quantity: 15,
        avgPrice: 300.00,
        currentPrice: 385.20,
        currentValue: 5778.00,
        gainLoss: 1278.00,
        returnPercentage: 28.40
      },
      {
        security: 'GOOGL',
        quantity: 8,
        avgPrice: 2500.00,
        currentPrice: 2750.00,
        currentValue: 22000.00,
        gainLoss: 2000.00,
        returnPercentage: 10.00
      }
    ]
  },

  // Budget Progress
  budgetProgress: [
    {
      category: 'Housing',
      budgetAmount: 2000,
      actualSpent: 1800,
      progressPercentage: 90.0,
      overBudget: false
    },
    {
      category: 'Food & Dining',
      budgetAmount: 800,
      actualSpent: 650,
      progressPercentage: 81.25,
      overBudget: false
    },
    {
      category: 'Transportation',
      budgetAmount: 600,
      actualSpent: 720,
      progressPercentage: 120.0,
      overBudget: true
    },
    {
      category: 'Entertainment',
      budgetAmount: 300,
      actualSpent: 180,
      progressPercentage: 60.0,
      overBudget: false
    }
  ],

  // Anomalies
  anomalies: [
    {
      date: '2024-01-10',
      payee: 'Luxury Hotel',
      amount: 450.00,
      type: 'Unusual Expense',
      score: 0.85,
      explanation: 'Significantly higher than typical hotel expenses'
    },
    {
      date: '2024-01-08',
      payee: 'Cryptocurrency Exchange',
      amount: 2500.00,
      type: 'Large Transaction',
      score: 0.92,
      explanation: 'Unusual large investment transaction'
    }
  ],

  // Chat Messages
  chatMessages: [
    {
      role: 'user',
      content: 'Show me my spending by category for last month',
      timestamp: '2024-01-15 10:30'
    },
    {
      role: 'assistant',
      content: 'Here\'s your spending breakdown for December 2023:\n\n• Housing: $1,800 (35.2%)\n• Food & Dining: $1,200 (17.6%)\n• Transportation: $800 (11.7%)\n• Entertainment: $600 (8.8%)\n• Healthcare: $450 (6.6%)\n• Shopping: $400 (5.9%)\n• Utilities: $350 (5.1%)\n• Other: $620 (9.1%)\n\nTotal: $5,220',
      timestamp: '2024-01-15 10:31'
    },
    {
      role: 'user',
      content: 'What are my biggest expenses this month?',
      timestamp: '2024-01-15 10:35'
    },
    {
      role: 'assistant',
      content: 'Your top expenses for January 2024 so far:\n\n1. Rent Payment: $1,800 (Jan 11)\n2. Whole Foods: $127.45 (Jan 12)\n3. Amazon: $89.99 (Jan 15)\n4. Shell Gas: $45.20 (Jan 14)\n5. Electric Bill: $125.30 (Jan 10)\n\nTotal spent: $2,187.94',
      timestamp: '2024-01-15 10:36'
    }
  ]
};

// Utility functions
function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(amount);
}

function formatPercentage(value) {
  return `${value.toFixed(1)}%`;
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

// Export for use in HTML files
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { sampleData, formatCurrency, formatPercentage, formatDate };
}
