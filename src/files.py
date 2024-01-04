import pandas as pd
import os
from tqdm import tqdm

from portfolio import Transaction


def read_stock_files(directory: str) -> pd.DataFrame:
    df_list = []
    for filename in tqdm(os.listdir(directory)):
        if not filename.endswith(".us.txt"):
            continue
        try:
            file_path = os.path.join(directory, filename)
            df = pd.read_csv(
                file_path,
                #parse_dates=["Date"],
                dtype={"Open": float, "High": float, "Low": float, "Close": float},
            )
            stock_name = filename.split(".")[0]
            df["Name"] = stock_name
            df_list.append(df)
        except pd.errors.EmptyDataError:
            continue
    all_data = pd.concat(df_list, ignore_index=True)
    return all_data


def write_transaction_file(file_path: str, transactions: list[Transaction]):
    with open(file_path, "w") as file:
        file.write(f"{len(transactions)}\n")

        for transaction in transactions:
            line = f"{transaction.day} {transaction.transaction_type} {transaction.stock.upper()} {transaction.count}\n"
            file.write(line)


def read_transaction_file(file_path: str) -> list[Transaction]:
    transactions = []
    with open(file_path, "r") as file:
        next(file)
        for line in file:
            parts = line.strip().split()
            # day = datetime.datetime.strptime(parts[0], "%Y-%m-%d").date()
            day = parts[0]
            transaction_type = parts[1]
            stock = parts[2].lower()
            count = int(parts[3])
            transaction = Transaction(day, transaction_type, stock, count)
            transactions.append(transaction)
    return transactions
