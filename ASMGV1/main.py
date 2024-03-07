from AlgorithmImports import *
from collections import deque
from QuantConnect.Indicators import *

class CustomIndicatorAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024,2,29)
        self.SetEndDate(2024,3,5)

        #  TODO: is the warm up period needed
        self.asgma_period = 25
        self.SetWarmup(self.asgma_period)
        self.tickers = ["SPY"]
        symbols = [ Symbol.Create(ticker, SecurityType.Equity, Market.USA) for ticker in self.tickers]
        self.SetUniverseSelection(ManualUniverseSelectionModel(symbols) )
        self.AddAlpha(MyAlphaModel())
        self.UniverseSettings.Resolution = Resolution.Minute
        self.Settings.RebalancePortfolioOnInsightChanges = True
        self.Settings.RebalancePortfolioOnSecurityChanges = True        
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(lambda time: None))
        self.AddRiskManagement(NullRiskManagementModel())
        self.SetExecution(ImmediateExecutionModel()) 


class MyAlphaModel(AlphaModel):
    symbol_data_by_symbol = {}

    def __init__(self):
        pass

    def Update(self, algorithm, data):
        if algorithm.IsWarmingUp:
            for symbol in self.symbol_data_by_symbol:
                pass

        
  
        insights = []
        for symbol, symbolData in self.symbol_data_by_symbol.items():
            # if symbolData.alma.IsReady and symbolData.gma.IsReady: 
            # algorithm.Log("a: "+str(symbolData.alma.Current.Value))
            algorithm.Log("ag," + str(algorithm.Time)+ "," +str(symbolData.alma.Current.Value) + "," +str(symbolData.gma.Value))
            # algorithm.Log("g: "+str(symbolData.gma.Value))
            # algorithm.Log("Insight down: "  + str(algorithm.Time)+ "SMA 8 Value: " + str(symbolData.sma_fast) + "SMA 21: " + str(symbolData.sma_slow))
            if symbolData.alma.Current.Value < symbolData.gma.Value:
                # algorithm.Log("Insight down: "  + str(algorithm.Time)+ "SMA 8 Value: " + str(symbolData.sma_fast) + "SMA 21: " + str(symbolData.sma_slow))
                insights.append(Insight.Price(symbolData.symbol, timedelta(365),InsightDirection.Down))
            elif symbolData.alma.Current.Value > symbolData.gma.Value:
                # algorithm.Log("Insight up: " + str(algorithm.Time)+ "... SMA 8 Value: " + str(symbolData.sma_fast) + "SMA 21: " + str(symbolData.sma_slow))
                insights.append(Insight.Price(symbolData.symbol, timedelta(365), InsightDirection.Up))

        return insights

    def OnSecuritiesChanged(self, algorithm, changes):
        for added in changes.AddedSecurities:
            self.symbol_data_by_symbol[added.Symbol] = SymbolData(added.Symbol, algorithm)

        for removed in changes.RemovedSecurities:
            symbol_data = self.symbol_data_by_symbol.pop(removed.Symbol, None)
            if symbol_data:
                symbol_data.dispose()
        
        
class SymbolData:
    def __init__(self, symbol, algorithm):
        self.symbol = symbol
        self.algorithm = algorithm 
        
        self.alma_period = 25
        self.offset = 0.85
        self.sigma1 = 7 
        self.gma_period = 15

        self.volatility_period = 20

        # TODO: Change to percentage difference 
        self.alma = ArnaudLegouxMovingAverage(period=self.alma_period, sigma=self.sigma1, offset=self.offset)
        self.sigma = StandardDeviation(self.volatility_period)
        self.gma = CustomIndicator(algorithm, self.gma_period)

        # Setup daily indicator consolidator
        self.consolidator = TradeBarConsolidator(timedelta(minutes=1))
        self.consolidator.DataConsolidated += self.CustomHandler
        algorithm.SubscriptionManager.AddConsolidator(self.symbol, self.consolidator)
    
    def CustomHandler(self, sender, consolidated):
        self.alma.Update(consolidated.Time, consolidated.Close)
        self.sigma.Update(consolidated.Time, consolidated.Close)
        self.gma.Update(consolidated.Time, self.alma, self.sigma)
        
    def dispose(self):
        self.algorithm.SubscriptionManager.RemoveConsolidator(self.symbol, self.consolidator)

class CustomIndicator(PythonIndicator):
    import math, numpy as np
    
    def __init__(self, algorithm, period=14):
        self.period = period
        self.queue = deque(maxlen=period)
        self.algorithm = algorithm
        # GMA period fixed as 7
        self.gmaq = deque(maxlen=7)
        self.gma_ema = ExponentialMovingAverage(period=7)
        self.Value = 0

    def Update(self, time_index, avpchange, std) -> bool:
        self.queue.append(avpchange.Current.Value) 
        self.window = np.array(self.queue)
        # TODO: Check percent difference
        count = len(self.window)
        gma_last = 0
        sum_of_weights = 0
        length = 14
        
        if std.IsReady:
            sigma = std.Current.Value
            # TODO: Set warm up period: done
            for i in (0,count-1):
                weight = np.exp(-np.power(((i - (length - 1)) / (2 * sigma)), 2) / 2)
                value = np.max(self.window[i]) + np.min(self.window[i])
                gma_last += (value * weight)
                sum_of_weights += weight
                
            
            gma_last = float((gma_last/sum_of_weights)/2)
            self.gmaq.append(gma_last)
            self.gma = np.array(self.gmaq)
            
            if len(self.gma)==7:
                # self.algorithm.Log(str(time_index)+str(self.gma))
                # self.algorithm.Log(str(self.window[-14:]))
                for gma_elem in self.gma:
                    self.gma_ema.Update(time_index, gma_elem)
                if self.gma_ema.IsReady:
                    # self.algorithm.Log(str(time_index)+','+str(self.gma_ema.Current.Value))
                    self.Value = self.gma_ema.Current.Value

        return self.gma_ema
