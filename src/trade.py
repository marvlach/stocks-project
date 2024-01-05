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

    def __handle_buy_low(self, rows: pd.DataFrame, budget: float):
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

    def trade(self, grind_factor: float = 1.0):
        end_of_time = pd.to_datetime(self.df["AllTimeMaxCloseDate"].max())
        days_to_start_mass_sell = int(1000)
        print("Day I'll start mass selling", end_of_time - pd.Timedelta(days=days_to_start_mass_sell))

        for day, stocks_today in self.df.groupby("Date"):
            
            sell_everything = (end_of_time - pd.to_datetime(day)) / pd.Timedelta(
                days=1
            ) < days_to_start_mass_sell

            sell_high_rebuy_close, sell_open_rebuy_low = self.__intraday_opportunity(
                stocks_today,
            )

            # the two are mutually exclusive; only one is True for each stock
            sell_high_rebuy_close: pd.Series = (sell_high_rebuy_close) & (
                ~sell_everything
            )
            sell_open_rebuy_low: pd.Series = (sell_open_rebuy_low) & (~sell_everything)

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
            #print("sell_open_buy_low_trades", sell_open_buy_low_trades)
            self.__execute_trades(day, sell_open_buy_low_trades, "sell-open")

            """  
            Miday
            """
            money_to_spent_on_buy = (
                self.portfolio.get_balance() - total_money_to_rebuy_on_low
            )
            stocks_i_want_to_buy: pd.Series = (
                (stocks_today["WantToBuy"] == 1)
                & (stocks_today["Low"] < money_to_spent_on_buy)
                & (~sell_high_rebuy_close)
                & (~sell_open_rebuy_low)
                & (~sell_everything)
            )

            buy_low_trades = (
                (
                    self.__handle_buy_low(
                        stocks_today.loc[stocks_i_want_to_buy],
                        money_to_spent_on_buy,
                    )
                )
                if stocks_i_want_to_buy.any()
                else {}
            )

            stocks_i_want_to_sell = (
                (stocks_today["WantToSell"] == 1)
                & (
                    stocks_today.index.get_level_values("Name").isin(
                        self.portfolio.get_stocks().keys()
                    )
                )
                # & ~is_intraday_only
            )
            sell_high_trades = self.__handle_sell(
                stocks_today.loc[stocks_i_want_to_sell],
            )

            sell_high_buy_close_trades = self.__handle_sell(
                stocks_today.loc[sell_high_rebuy_close],
            )

            # execute everything
            # buy low
            #print("buy_low_trades", buy_low_trades)
            self.__execute_trades(day, buy_low_trades, "buy-low")

            # sell high
            #print("sell_high_trades", sell_high_trades)
            self.__execute_trades(day, sell_high_trades, "sell-high")

            # rebuy low
            #print("sell_open_buy_low_trades", sell_open_buy_low_trades)
            self.__execute_trades(day, sell_open_buy_low_trades, "buy-low")

            # sell high to rebuy close
            #print("sell_high_buy_close_trades", sell_high_buy_close_trades)
            self.__execute_trades(day, sell_high_buy_close_trades, "sell-high")

            # close phase rebuy on close
            #print("sell_high_buy_close_trades", sell_high_buy_close_trades)
            self.__execute_trades(day, sell_high_buy_close_trades, "buy-close")

            #print("\n")


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
