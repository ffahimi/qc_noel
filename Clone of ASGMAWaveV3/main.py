from AlgorithmImports import *
from collections import deque
from QuantConnect.Indicators import *
import math, numpy as np

class CustomIndicatorAlgorithm(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024,2,27)
        self.SetEndDate(2024,2,28)

        self.asgma_period = 40
        # the warm up period needed (25+1 as we use the percentage difference in our indicators which requires one more element
        # warm up updated/increased to 35 = channel_length + signal_length + average_length for the wavetrend indicator 
        # TODO: make warm up a variable
        # TODO: move warm up to the indicators 
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
        # self.file = self.Download(url)
        self.tickers_df = pandas.read_csv(StringIO(self.file))
        
class MyAlphaModel(AlphaModel):

    symbol_data_by_symbol = {}
    def __init__(self):
        self.previous_insight_direction = 0

    def Update(self, algorithm, data):
        if algorithm.IsWarmingUp:
            for symbol in self.symbol_data_by_symbol:
                pass
            
        insights = []
        for symbol, symbolData in self.symbol_data_by_symbol.items():
            algorithm.Log("agap2," + str(algorithm.Time)+ "," + str(symbolData.current_close) + "," + str(symbolData.wt.Value) + "," + str(symbolData.wt.wt2.Current.Value) + ","+str(symbolData.alma.Value) + "," +str(symbolData.gma.Value) + "," + str(symbolData.alma2.Current.Value) + "," + str(symbolData.alma.current_prctdiff))
            # algorithm.Log("agap2," + str(algorithm.Time)+ "," + str(symbolData.current_close) + "," +str(symbolData.alma.Value) + "," +str(symbolData.gma.Value) + "," + str(symbolData.alma2.Current.Value) + "," + str(symbolData.alma.current_prctdiff))
           
            # if symbolData.alma.Current.Value < symbolData.gma.Value:
            #     self.previous_insight_direction = -1 if self.previous_insight_direction == 0 else self.previous_insight_direction
            #     # check only for cross under
            #     if self.previous_insight_direction != -1:
            #         self.previous_insight_direction = -1
            #         insights.append(Insight.Price(symbolData.symbol, timedelta(365),InsightDirection.Down))
            # elif symbolData.alma.Current.Value > symbolData.gma.Value:
            #     self.previous_insight_direction = 1 if self.previous_insight_direction == 0 else self.previous_insight_direction
            #     # check only for cross over
            #     if self.previous_insight_direction != 1:
            #         self.previous_insight_direction = 1
            #         insights.append(Insight.Price(symbolData.symbol, timedelta(365), InsightDirection.Up))
        
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
        self.gma_period = 14
        self.volatility_period = 20
        self.current_close = 0
        self.algorithm = algorithm

        # TODO: Change to percentage difference: Done 
        self.alma = ALMAIndicator(algorithm, period=self.alma_period, sigma=self.sigma1, offset=self.offset)
        self.sigma = StandardDeviation(self.volatility_period)
        self.gma = GMAIndicator(algorithm, self.gma_period)
        self.alma2 = ArnaudLegouxMovingAverage(self.alma_period, self.sigma1, self.offset)
        self.wt = WaveTrend(algorithm, channel_length=10, average_length=21, signal_length=4)
        
        # Setup daily indicator consolidator: Done
        self.consolidator = TradeBarConsolidator(timedelta(minutes=1))
        self.consolidator.DataConsolidated += self.CustomHandler
        algorithm.SubscriptionManager.AddConsolidator(self.symbol, self.consolidator)
    
    def CustomHandler(self, sender, consolidated):
        # self.algorithm.Log(str(self.algorithm.Time)+","+str(consolidated.Time)+","+str(consolidated.Close) + ","+ str(self.alma.current_close))
        self.alma.Update(consolidated.Time, consolidated.Close)
        self.alma2.Update(consolidated.Time, consolidated.Close)
        self.sigma.Update(consolidated.Time, consolidated.Close)
        self.gma.Update(consolidated.Time, self.alma, self.sigma)
        # TODO: Check the consolidated close high and low are the right attributes 
        hlc3 = float(consolidated.Close + consolidated.High + consolidated.Low)/3
        self.wt.Update(consolidated.Time, hlc3)
        self.current_close = consolidated.Close

    def dispose(self):
        self.algorithm.SubscriptionManager.RemoveConsolidator(self.symbol, self.consolidator)

class GMAIndicator(PythonIndicator):

    # The GMA indicator with percentage change of close as the input
    def __init__(self, algorithm, period=14):
        self.period = period
        self.queue = deque(maxlen=period)
        self.algorithm = algorithm
        # GMA period fixed as 7
        self.gmaq = deque(maxlen=7)
        self.gma_ema = ExponentialMovingAverage(period=7)
        self.Value = 0

    def Update(self, time_index, avpchange, std) -> bool:
        self.queue.append(avpchange.Value) 
        self.window = np.array(self.queue)
        
        count = len(self.window)
        gma_last = 0
        sum_of_weights = 0
        length = 14

        if std.IsReady:
            sigma = std.Current.Value
            for i in (0,count-1):
                # weight = math.exp(-math.pow(((i - (length - 1)) / (2 * sigma)), 2) / 2)
                weight = np.exp(-np.power(((i - (length - 1)) / (2 * sigma)), 2) / 2)
                # value = ta.highest(avpchange, i + 1) + ta.lowest(avpchange, i + 1)
                value = np.max(self.window[-i:]) + np.min(self.window[-i:])
                #  gma := gma + (value * weight)
                gma_last += (value * weight)
                # sumOfWeights := sumOfWeights + weight
                sum_of_weights += weight
            
            # gma := (gma / sumOfWeights) / 2
            gma_last = float(gma_last/sum_of_weights)/2
            self.gmaq.append(gma_last)
            self.gma = np.array(self.gmaq)
            
            # gma:= ta.ema(gma, 7)
            if len(self.gma)==7:
                # self.algorithm.Log("gma: "+ str(self.gma))
                for gma_elem in self.gma:
                    self.gma_ema.Update(time_index, gma_elem)
                if self.gma_ema.IsReady:
                    self.Value = self.gma_ema.Current.Value

        return self.gma_ema

class ALMAIndicator(PythonIndicator):
    
    # The alma indicator with percentage change of close as the input
    def __init__(self, algorithm, period=25, sigma=7, offset=0.85):
        # length1 = 25
        # offset = 0.85
        # sigma1 = 7
        self.period = period
        self.sigma = sigma
        self.offset = offset
        # period+1 is length because we are using a percentage change which will deduce the useful range by 1
        self.queue = deque(maxlen=(period+1))
        self.algorithm = algorithm
        self.alma = ArnaudLegouxMovingAverage(period, sigma, offset)
        self.Value = 0
        self.current_close = 0
        self.current_prctdiff = 0

    def Update(self, time_index, close_price) -> bool:
        # appending the right side of the queue the incoming close price after consolidation
        self.queue.append(close_price) 
        self.current_close = close_price
        self.window = np.array(self.queue)
        # this is the formula to calculate percentage diff
         # pchange = ta.change(src, 1) / src * 100
        # self.algorithm.Log(str(self.window[-1]))

        if len(self.window) == self.period+1:
            self.prctdiff = np.divide(self.window[1:] - self.window[:-1],self.window[1:])*100
            for prct_elem in self.prctdiff:
                    self.alma.Update(time_index, prct_elem)
                
            if self.alma.IsReady:
                self.Value = self.alma.Current.Value
                self.current_prctdiff = self.prctdiff[-1]
                
        return self.alma

class WaveTrend(PythonIndicator):
    
    # The alma indicator with percentage change of close as the input
    def __init__(self, algorithm, channel_length=10, average_length=21, signal_length=4):
        self.algorithm = algorithm
        self.esa = ExponentialMovingAverage(channel_length)
        self.d = ExponentialMovingAverage(channel_length)
        self.tci = ExponentialMovingAverage(average_length)
        self.wt1 = 0
        self.wt2 = ExponentialMovingAverage(signal_length)
        self.Value = 0
        self.current_hlc3 = 0
        
        self.channel_length = channel_length
        self.average_length = average_length
        self.signal_length = signal_length

        # // WaveTrend calculation
        # esa = ta.ema(src, channelLength)
        # d = ta.ema(math.abs(src - esa), channelLength)
        # ci = (src - esa) / (0.015 * d)
        # tci = ta.ema(ci, averageLength)
        # wt1 = tci
        # wt2 = ta.sma(wt1, signalLength)


    def Update(self, time_index, hlc3) -> bool:
        self.esa.Update(time_index, hlc3)
        
        if self.esa.IsReady:
            esa = self.esa.Current.Value
            # self.algorithm.Log("esa: "+str(esa) + "," + str(hlc3))
            # d = ta.ema(math.abs(src - esa), channelLength)
            # self.algorithm.Log(str(np.abs(hlc3-esa)))
            self.d.Update(time_index, float(np.abs(hlc3-esa)))
            
            if self.d.IsReady:    
                d = self.d.Current.Value
                # self.algorithm.Log("d:"+str(d))
                ci = (hlc3 - esa)/(0.015+d)
                self.tci.Update(time_index, ci)
                
                if self.tci.IsReady:
                    tci = self.tci.Current.Value
                    self.wt1 = tci
                    self.wt2.Update(time_index, float(self.wt1))
        
        self.Value = self.wt1

        return self.wt2
