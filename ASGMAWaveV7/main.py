from AlgorithmImports import *
from collections import deque
from QuantConnect.Indicators import *
import math, numpy as np
import pandas
from io import StringIO
from indicators import *
from alpha import *

class CustomIndicatorAlgorithm(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024,3,5)
        self.SetEndDate(2024,3,6)
        self.SetCash(100000)

        # self.SetTimeZone("Europe/London")
        url = 'https://qcfiles.s3.eu-north-1.amazonaws.com/AMEX_SPY_1min.csv'
        self.file = self.Download(url)
        self.tickers_df = pandas.read_csv(StringIO(self.file))

        self.asgma_period = 40
        # the warm up period needed (25+1 as we use the percentage difference in our indicators which requires one more element
        # warm up updated/increased to 35 = channel_length + signal_length + average_length for the wavetrend indicator 
        # TODO: make warm up a variable
        # TODO: move warm up to the indicators 
        self.SetWarmup(1)
        self.tickers = ["SPY"]
        symbols = [ Symbol.Create(ticker, SecurityType.Equity, Market.USA) for ticker in self.tickers]
        self.Settings.RebalancePortfolioOnInsightChanges = True
        self.Settings.RebalancePortfolioOnSecurityChanges = False
        self.SetUniverseSelection(ManualUniverseSelectionModel(symbols) )
        self.AddAlpha(MyAlphaModel())
        self.UniverseSettings.Resolution = Resolution.Minute
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.SetPortfolioConstruction(InsightWeightingPortfolioConstructionModel(self.RebalanceFunction, PortfolioBias.LongShort))
        # self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(lambda time: None, PortfolioBias.LongShort))
        self.SetExecution(ImmediateExecutionModel())
        
        self.SetRiskManagement(MaximumDrawdownPercentPerSecurity(0.2))
        
    def OnOrderEvent(self, orderEvent):
        order = self.Transactions.GetOrderById(orderEvent.OrderId)
        self.Debug(f"{self.Time} OrderEvent: {orderEvent}. Current holding for {order.Symbol}: Invested={self.Portfolio[order.Symbol].Invested}, Quantity={self.Portfolio[order.Symbol].Quantity}")

    def RebalanceFunction(self, time):
        return None


        
