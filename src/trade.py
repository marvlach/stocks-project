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


def trade_1(df: pd.DataFrame, portfolio: Portfolio):
    """
    PoC
    """
    for label, row in df.iterrows():
        # intra day good day to sell high, rebuy on close
        sell_high_rebuy_close = (row["Low"] == row["Close"]) & (
            row["High"] > row["Low"]
        )
        sell_open_rebuy_low = (row["Open"] == row["High"]) & (row["High"] > row["Low"])

        opening = []
        during = []
        closing = []
        if (
            sell_high_rebuy_close or sell_open_rebuy_low
        ) and portfolio.get_stocks().get(label[1], 0) > 0:
            if sell_high_rebuy_close:
                how_many = min(
                    portfolio.get_stocks().get(label[1]), int(0.09 * row["Volume"])
                )
                during.append((row, portfolio.sell, "sell-high", how_many))
                closing.append((row, portfolio.buy, "buy-close", how_many))

            elif sell_open_rebuy_low:
                how_many = min(
                    portfolio.get_stocks().get(label[1]), int(0.09 * row["Volume"])
                )
                opening.append((row, portfolio.sell, "sell-open", how_many))
                during.append((row, portfolio.buy, "buy-low", how_many))
        else:
            # what to buy
            if row["WantToBuy"] == 1 and portfolio.get_balance() > row["Low"]:
                how_many = min(
                    int(portfolio.get_balance() / row["Low"]), int(0.09 * row["Volume"])
                )
                during.append((row, portfolio.buy, "buy-low", how_many))
            # sell
            if row["WantToSell"] == 1 and portfolio.get_stocks().get(label[1], 0) > 0:
                how_many = min(
                    portfolio.get_stocks().get(label[1]), int(0.09 * row["Volume"])
                )
                during.append((row, portfolio.sell, "sell-high", how_many))

        if not opening and not during and not closing:
            print("noop")
        for transaction_list in [opening, during, closing]:
            for transaction in transaction_list:
                row, method, transaction_type, count = transaction
                # print(transaction)
                method(row, transaction_type, count)

        print(label, portfolio.get_stocks(), portfolio.get_balance())
