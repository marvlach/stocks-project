from math import ceil
import pandas as pd
from portfolio import Portfolio, Transaction
import random


def evaluate_transactions(df: pd.DataFrame, transactions: list[Transaction]):
    portfolio = Portfolio()

    for transaction in transactions:
        row_df = df.loc[(transaction.day, transaction.stock)]
        if transaction.transaction_type.startswith("buy"):
            portfolio.buy(row_df, transaction.transaction_type, transaction.count)
        else:
            portfolio.sell(row_df, transaction.transaction_type, transaction.count)
    return portfolio


class Trader:
    def __init__(self, df: pd.DataFrame, portfolio: Portfolio) -> None:
        self.df = df
        self.portfolio = portfolio

    def __intraday_opportunity(
        self,
        stocks_today: pd.DataFrame,
    ) -> tuple[pd.Series, pd.Series]:
        sell_high_rebuy_close = (
            (stocks_today["Low"] == stocks_today["Close"])
            & (stocks_today["High"] > stocks_today["Low"])
            & (
                stocks_today.index.get_level_values("Name").isin(
                    self.portfolio.get_stocks().keys()
                )
            )
            & (stocks_today["WantToSell"] == 0)
        )

        sell_open_rebuy_low = (
            (stocks_today["Open"] == stocks_today["High"])
            & (stocks_today["High"] > stocks_today["Low"])
            & (
                stocks_today.index.get_level_values("Name").isin(
                    self.portfolio.get_stocks().keys()
                )
            )
            & (stocks_today["WantToSell"] == 0)
            & (~sell_high_rebuy_close)
        )
        return sell_high_rebuy_close, sell_open_rebuy_low

    def __handle_sell(self, rows: pd.DataFrame):
        """rows contains rows I want to sell"""
        trades: dict[str, int] = dict()
        for (_, stock_name), stock_info in rows.iterrows():
            how_many = min(
                self.portfolio.get_stocks().get(stock_name),
                int(0.1 * stock_info["Volume"]),
            )
            trades[stock_name] = how_many
        return trades

    def __handle_buy_low(self, rows: pd.DataFrame, budget: float, days_until_end: int):
        if rows.shape[0] == 0 or budget == 0:
            return dict()

        # TODO: make the split more clever
        trades: dict[str, int] = dict()
        # split budget equally
        budget_each = budget / rows.shape[0]
        # print(f'Total budget {budget}: {rows.shape[0]}-way split; {budget_each} each')
        # rows contain stocks that want to buy
        for (_, stock_name), stock_info in rows.iterrows():
            how_many = min(
                int(budget_each / stock_info["Low"]), int(0.1 * stock_info["Volume"])
            )
            trades[stock_name] = how_many
        trades = {st: count for st, count in trades.items() if count > 0}
        return trades

    def __execute_trades(self, day: str, trades: dict[str, int], trade_type: str):
        for stock_name, stock_count in trades.items():
            if trade_type.startswith("buy"):
                self.portfolio.buy(
                    self.df.loc[(day, stock_name)],
                    trade_type,
                    stock_count,
                )
            else:
                self.portfolio.sell(
                    self.df.loc[(day, stock_name)],
                    trade_type,
                    stock_count,
                )

    def trade(self, days_to_start_mass_sell: int):
        end_of_time = pd.to_datetime(self.df["AllTimeMaxCloseDate"].max())
        print(
            "Day I'll start mass selling",
            end_of_time - pd.Timedelta(days=days_to_start_mass_sell),
        )
        start_of_mass_sell = end_of_time - pd.Timedelta(days=days_to_start_mass_sell)
        start_of_dropping_rebuy_rate = pd.to_datetime(
            self.df["AllTimeMinCloseDate"].min()
        )

        for day, stocks_today in self.df.groupby("Date"):
            """if pd.to_datetime(day) < start_of_dropping_rebuy_rate:
                rebuy_rate = 1
            elif pd.to_datetime(day) < start_of_mass_sell:
                day_diff = (pd.to_datetime(day) - start_of_mass_sell) / pd.Timedelta(
                    days=1
                )
                rebuy_rate = (
                    (1 - 0)
                    / (
                        (start_of_dropping_rebuy_rate - start_of_mass_sell)
                        / pd.Timedelta(days=1)
                    )
                ) * day_diff
                # print(day, rebuy_rate)
            else:
                rebuy_rate = 0"""

            todays_stocks_i_have = stocks_today.index.get_level_values("Name").map(
                lambda x: self.portfolio.get_stocks().get(x, 0)
            )
            todays_stocks_i_have_to_sell = (
                todays_stocks_i_have >= stocks_today["CanSell"]
            )

            sell_everything = (end_of_time - pd.to_datetime(day)) / pd.Timedelta(
                days=1
            ) < days_to_start_mass_sell

            sell_high_rebuy_close, sell_open_rebuy_low = self.__intraday_opportunity(
                stocks_today,
            )

            # the two are mutually exclusive; only one is True for each stock
            sell_high_rebuy_close: pd.Series = (
                (sell_high_rebuy_close)
                & (~sell_everything)
                & (~todays_stocks_i_have_to_sell)
            )
            sell_open_rebuy_low: pd.Series = (
                (sell_open_rebuy_low)
                & (~sell_everything)
                & (~todays_stocks_i_have_to_sell)
            )

            """ 
            Opening
            """
            sell_open_buy_low_trades = self.__handle_sell(
                stocks_today.loc[sell_open_rebuy_low],
            )
            # make sure to reserve some money to buy back on Low
            total_money_to_rebuy_on_low = (
                sum(
                    [
                        stock_count * stocks_today.loc[(day, stock_name), "Low"]
                        for stock_name, stock_count in sell_open_buy_low_trades.items()
                    ]
                )
                if sell_open_buy_low_trades
                else 0
            )

            # execute open phase
            # print("sell_open_buy_low_trades", sell_open_buy_low_trades)
            self.__execute_trades(day, sell_open_buy_low_trades, "sell-open")

            """  
            Miday
            """
            money_to_spent_on_buy = (
                self.portfolio.get_balance() - total_money_to_rebuy_on_low
            )
            # print('\nmoney_to_spent_on_buy', money_to_spent_on_buy)
            # money_to_spent_on_buy = (rebuy_rate**2) * money_to_spent_on_buy
            # print('money_to_spent_on_buy', money_to_spent_on_buy)
            stocks_i_want_to_buy: pd.Series = (
                (stocks_today["WantToBuy"] == 1)
                & (stocks_today["Low"] < money_to_spent_on_buy)
                & (~sell_high_rebuy_close)
                & (~sell_open_rebuy_low)
                & (~sell_everything)
                & (~todays_stocks_i_have_to_sell)
            )

            buy_low_trades = self.__handle_buy_low(
                stocks_today.loc[stocks_i_want_to_buy],
                money_to_spent_on_buy,
                (end_of_time - pd.to_datetime(day)) / pd.Timedelta(days=1),
            )

            stocks_i_want_to_sell = (
                (stocks_today["WantToSell"] == 1)
                & (
                    stocks_today.index.get_level_values("Name").isin(
                        self.portfolio.get_stocks().keys()
                    )
                )
            ) | todays_stocks_i_have_to_sell
            sell_high_trades = self.__handle_sell(
                stocks_today.loc[stocks_i_want_to_sell],
            )

            sell_high_buy_close_trades = self.__handle_sell(
                stocks_today.loc[sell_high_rebuy_close],
            )

            # execute everything
            # buy low
            # print("buy_low_trades", buy_low_trades)
            self.__execute_trades(day, buy_low_trades, "buy-low")

            # sell high
            # print("sell_high_trades", sell_high_trades)
            self.__execute_trades(day, sell_high_trades, "sell-high")

            # rebuy low
            # print("sell_open_buy_low_trades", sell_open_buy_low_trades)
            """ rebuy_low_trades = {
                # stock_name: ceil((rebuy_rate ** 2) * stock_count)
                stock_name: stock_count
                for stock_name, stock_count in sell_open_buy_low_trades.items()
                if self.df.loc[(day, stock_name), "WantToBuy"]
                == 1  # and random.random() < (1 - self.df.loc[(day, stock_name), 'PercentageIncrease'])
            } """
            self.__execute_trades(day, sell_open_buy_low_trades, "buy-low")

            # sell high to rebuy close
            # print("sell_high_buy_close_trades", sell_high_buy_close_trades)
            self.__execute_trades(day, sell_high_buy_close_trades, "sell-high")

            # close phase rebuy on close
            # print("sell_high_buy_close_trades", sell_high_buy_close_trades)
            """ rebuy_close_trades = {
                # stock_name: ceil((rebuy_rate ** 2) * stock_count)
                stock_name: stock_count
                for stock_name, stock_count in sell_high_buy_close_trades.items()
                if self.df.loc[(day, stock_name), "WantToBuy"]
                == 1  # and random.random() < (1 - self.df.loc[(day, stock_name), 'PercentageIncrease'])
            } """
            self.__execute_trades(day, sell_high_buy_close_trades, "buy-close")

            # print("\n")
