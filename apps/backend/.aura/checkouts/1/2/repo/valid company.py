import pandas

company_df = pandas.read_csv("company_details.csv")

print(company_df.head())

# filter the company which has shares outstanding, some of them are none

company_df = company_df[company_df["Shares Outstanding"].notna()]

company_df.to_csv("valid_company_details.csv", index=False)
