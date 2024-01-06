import pandas as pd
from portfolio import Portfolio, Transaction


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
        """
        For intraday we target stocks that:

        - Exhibit their Low on Close so that se can sell on High
        and rebuy them on Low or

        - stocks that exhibit their High on Open so that we can
        sell them on Open and rebuy all of them on Low

        Only one of those can be active per stock. If both then
        we choose Sell High Buy Close==Low
        """
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
        """
        For every stock I want to sell, I sell as much as I can
        """
        trades: dict[str, int] = dict()
        for (_, stock_name), stock_info in rows.iterrows():
            how_many = min(
                self.portfolio.get_stocks().get(stock_name),
                int(0.1 * stock_info["Volume"]),
            )
            trades[stock_name] = how_many
        return trades

    def __handle_buy(self, rows: pd.DataFrame, budget: float):
        """
        For every stock I want to buy, I split my budget equally
        and buy as much as I can
        TODO: make the split more clever
        """
        if rows.shape[0] == 0 or budget == 0:
            return dict()

        trades: dict[str, int] = dict()

        budget_each = budget / rows.shape[0]

        for (_, stock_name), stock_info in rows.iterrows():
            how_many = min(
                int(budget_each / stock_info["Low"]), int(0.1 * stock_info["Volume"])
            )
            trades[stock_name] = how_many
        trades = {st: count for st, count in trades.items() if count > 0}
        return trades

    def __execute_trades(self, day: str, trades: dict[str, int], trade_type: str):
        """
        Execute trades on the dictionary by calling the portfolio methods
        """
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

    def trade(self):
        """  
        Trades everyday

        - Intraday trades the stocks according to __intraday_opportunity.

        - If I have more stocks that I can sell in the future start selling now

        - Buy WantToBuy stocks unless there are intraday-traded today or for sell

        - Sell WantToSell stocks
        
        """
        for day, stocks_today in self.df.groupby("Date"):
            todays_stocks_i_have = stocks_today.index.get_level_values("Name").map(
                lambda x: self.portfolio.get_stocks().get(x, 0)
            )

            todays_stocks_i_have_to_sell = (
                todays_stocks_i_have >= stocks_today["MaxCanSellUntilEnd"]
            )

            sell_high_rebuy_close, sell_open_rebuy_low = self.__intraday_opportunity(
                stocks_today,
            )

            # the two are mutually exclusive; only one is True for each stock
            sell_high_rebuy_close: pd.Series = (sell_high_rebuy_close) & (
                ~todays_stocks_i_have_to_sell
            )

            sell_open_rebuy_low: pd.Series = (sell_open_rebuy_low) & (
                ~todays_stocks_i_have_to_sell
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
            self.__execute_trades(day, sell_open_buy_low_trades, "sell-open")

            """  
            Miday
            """
            money_to_spent_on_buy = (
                self.portfolio.get_balance() - total_money_to_rebuy_on_low
            )

            # only buy stocks that are not intraday traded today and not for sell
            stocks_i_want_to_buy: pd.Series = (
                (stocks_today["WantToBuy"] == 1)
                & (stocks_today["Low"] < money_to_spent_on_buy)
                & (~sell_high_rebuy_close)
                & (~sell_open_rebuy_low)
                & (~todays_stocks_i_have_to_sell)
            )

            buy_low_trades = self.__handle_buy(
                stocks_today.loc[stocks_i_want_to_buy],
                money_to_spent_on_buy,
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
            self.__execute_trades(day, buy_low_trades, "buy-low")

            # sell high
            self.__execute_trades(day, sell_high_trades, "sell-high")

            # rebuy low
            self.__execute_trades(day, sell_open_buy_low_trades, "buy-low")

            # sell high to rebuy close; no need to check for money, I won't run out
            self.__execute_trades(day, sell_high_buy_close_trades, "sell-high")

            """  
            Closing
            """
            # rebuy on close
            self.__execute_trades(day, sell_high_buy_close_trades, "buy-close")

