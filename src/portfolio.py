import datetime
from dataclasses import dataclass

import pandas as pd


@dataclass
class Transaction:
    day: datetime.date
    transaction_type: str
    stock: str
    count: int


class Portfolio:
    def __init__(self) -> None:
        self.balance: float = 1
        self.stocks: dict[str, int] = dict()
        self.transaction_history: list[Transaction] = []

    def __get_price_column_from_transaction_type(self, transaction_type: str) -> str:
        return {
            "buy-open": "Open",
            "sell-open": "Open",
            "buy-low": "Low",
            "sell-high": "High",
            "buy-close": "Close",
            "sell-close": "Close",
        }[transaction_type]

    def __valid_buy_transaction(self, transaction_type):
        if transaction_type not in {"buy-open", "buy-low", "buy-close"}:
            raise ValueError("Invalid transaction type for method buy")

    def __valid_sell_transaction(self, transaction_type):
        if transaction_type not in {"sell-open", "sell-high", "sell-close"}:
            raise ValueError("Invalid transaction type for method sell")

    def __valid_arguments(self, df_row: pd.Series, count: int):
        if not isinstance(count, int) or count <= 0:
            raise TypeError("count needs to be positive integer")

        """ valid_cols = {"Open", "High", "Low", "Close", "Volume"}
        if set(df_row.index) != valid_cols:
            raise ValueError(f"Columns need to be {valid_cols}") 
        """

        row_date, _ = df_row.name
        if self.transaction_history and row_date < self.transaction_history[-1].day:
            raise ValueError("Tried to append new transaction in previous date")

        if count > 0.1 * df_row["Volume"]:
            raise ValueError("Cannot buy more than 10'%' of daily volume")

    def __update_transaction_history(
        self, date, name, transaction_type: str, count: int
    ):
        self.transaction_history.append(
            Transaction(
                day=date,
                transaction_type=transaction_type,
                stock=name,
                count=count,
            )
        )

    def get_balance(self):
        return self.balance

    def get_stocks(self):
        return self.stocks
    
    def get_evaluation(self, df: pd.DataFrame, day: datetime.date):
        return df.loc[
            pd.IndexSlice[day, self.stocks.keys()],
            "Close",
        ].sum()

    def buy(self, df_row: pd.Series, transaction_type: str, count: int):
        self.__valid_arguments(df_row, count)
        self.__valid_buy_transaction(transaction_type)

        # valid buy
        row_date, row_name = df_row.name

        price = df_row[self.__get_price_column_from_transaction_type(transaction_type)]
        money = count * price
        if money > self.balance:
            raise ValueError(f"Cannot spent more {money} than your balance {self.balance}")

        # update
        if row_name in self.stocks:
            self.stocks[row_name] += count
        else:
            self.stocks[row_name] = count
        self.balance -= money
        self.__update_transaction_history(row_date, row_name, transaction_type, count)

    def sell(self, df_row: pd.Series, transaction_type: str, count: int):
        self.__valid_arguments(df_row, count)
        self.__valid_sell_transaction(transaction_type)

        # valid sell
        row_date, row_name = df_row.name

        if row_name not in self.stocks or count > self.stocks[row_name]:
            raise ValueError(
                f"Cannot sell more {row_name} stocks {count} than you own {self.stocks[row_name]}"
            )

        price = df_row[self.__get_price_column_from_transaction_type(transaction_type)]
        money = count * price

        # update
        self.stocks[row_name] -= count
        if self.stocks[row_name] == 0:
            del self.stocks[row_name]
        self.balance += money
        self.__update_transaction_history(row_date, row_name, transaction_type, count)
