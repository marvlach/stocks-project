import pandas as pd

from portfolio import Portfolio, Transaction


def evaluate_transactions(df: pd.DataFrame, transactions: list[Transaction]):
    portfolio = Portfolio()

    for transaction in transactions:
        print(transaction)
        row_df = df.loc[(transaction.day, transaction.stock)]
        print(row_df)
        if transaction.transaction_type.startswith("buy"):
            portfolio.buy(row_df, transaction.transaction_type, transaction.count)
        else:
            portfolio.sell(row_df, transaction.transaction_type, transaction.count)
    return portfolio