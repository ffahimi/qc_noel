from AlgorithmImports import *
from collections import deque
from QuantConnect.Indicators import *
import math, numpy as np
import pandas
from io import StringIO

class CustomIndicatorAlgorithm(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024,2,9)
        # self.SetEndDate(2024,2,14)
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
        self.SetPortfolioConstruction(InsightWeightingPortfolioConstructionModel(self.RebalanceFunction, PortfolioBias.LongShort))
        # self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel(lambda time: None, PortfolioBias.LongShort))
        self.SetExecution(ImmediateExecutionModel())
        
        self.SetRiskManagement(MaximumDrawdownPercentPerSecurity(0.2))
        
    def OnOrderEvent(self, orderEvent):
        order = self.Transactions.GetOrderById(orderEvent.OrderId)
        self.Debug(f"{self.Time} OrderEvent: {orderEvent}. Current holding for {order.Symbol}: Invested={self.Portfolio[order.Symbol].Invested}, Quantity={self.Portfolio[order.Symbol].Quantity}")

    def RebalanceFunction(self, time):
        return None

class MyAlphaModel(AlphaModel):
    def __init__(self):
        
        self.symbol_directions = {}  # Dictionary to track the current direction for each symbol
        self.symbol_data_by_symbol = {}

    def Update(self, algorithm, data):
        insights = []
        weight = 0
        if algorithm.IsWarmingUp:
            for symbol in self.symbol_data_by_symbol:
                pass

        for symbol, symbolData in self.symbol_data_by_symbol.items():
            algorithm.Log(f"------------------")
            algorithm.Log(f"Checking conditions for symbol: {symbol} {symbol.Value}")
            algorithm.Log(f"Invested={algorithm.Portfolio[symbol].Invested}, Quantity={algorithm.Portfolio[symbol].Quantity}")

            newDirection = None
            if symbolData.wt.Value < -70 and symbolData.alma.Value >= symbolData.gma.Value:
                newDirection = InsightDirection.Up
                weight = (-70 - symbolData.wt.Value)/30
            elif symbolData.wt.Value > 70 and symbolData.alma.Value < symbolData.gma.Value:
                newDirection = InsightDirection.Down
                weight = (symbolData.wt.Value-70)/30
            if newDirection is not None:
                # Check if we have an existing position and its direction
                currentHolding = algorithm.Portfolio[symbol].Invested and algorithm.Portfolio[symbol].IsLong
                currentDirection = InsightDirection.Up if currentHolding else InsightDirection.Down

                # Determine if the new state is opposite to the current holding direction
                isNewDirection = (newDirection != currentDirection)
                isNotInvestedOrOpposite = not algorithm.Portfolio[symbol].Invested or (algorithm.Portfolio[symbol].Invested and isNewDirection)

                if isNotInvestedOrOpposite:
                    algorithm.Log(f"Insight {newDirection} for {symbol.Value}")
                    # Generate insight only if not invested or if wanting to trade in opposite direction
                    insight = Insight.Price(symbol, timedelta(days=1), newDirection, None, None, None, 0.6)
                    insights.append(insight)
                    self.symbol_directions[symbol] = newDirection  # Update the direction for this symbol
                else:
                    algorithm.Log(f"Not invested or opposite, so not doing anything.")
        
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
        self.ema = ExponentialMovingAverage(9, 0.5)

        # Setup daily indicator consolidator: Done
        self.consolidator = TradeBarConsolidator(timedelta(minutes=1))
        self.consolidator.DataConsolidated += self.CustomHandler
        algorithm.SubscriptionManager.AddConsolidator(self.symbol, self.consolidator)
    
    def CustomHandler(self, sender, consolidated):
        # self.algorithm.Log(str(self.algorithm.Time)+","+str(consolidated.Time)+","+str(consolidated.Close) + ","+ str(self.alma.current_close))
        self.alma.Update(consolidated.Time, consolidated.Close)
        self.alma2.Update(consolidated.Time, consolidated.Close)
        self.sigma.Update(consolidated.Time, consolidated.Close)
        self.ema.Update(consolidated.Time, consolidated.Close)
        self.gma.Update(consolidated.Time, self.alma, self.sigma)
        # TODO: Check the consolidated close high and low are the right attributes 
        hlc3 = float(consolidated.Close + consolidated.High + consolidated.Low)/3
        self.wt.Update(consolidated.Time, hlc3)
        self.current_close = consolidated.Close
        self.current_open = consolidated.Open
        self.current_high = consolidated.High
        self.current_low = consolidated.Low
        self.current_time = consolidated.Time

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
        self.d = StandardDeviation(channel_length)
        self.tci = ExponentialMovingAverage(average_length)
        self.wt1 = 0
        self.wt2 = SimpleMovingAverage(signal_length)
        self.Value = 0
        self.current_hlc3 = 0
        
        self.channel_length = channel_length
        self.average_length = average_length
        self.signal_length = signal_length

    def Update(self, time_index, hlc3) -> bool:
        self.current_hlc3 = hlc3
        self.esa.Update(time_index, hlc3)
        self.d.Update(time_index, hlc3)

        if self.esa.IsReady:
            esa = self.esa.Current.Value

        if self.d.IsReady:    
            d = self.d.Current.Value
            ci = (hlc3 - esa)/(d)*100
            self.tci.Update(time_index, ci)
                
            if self.tci.IsReady:
                tci = self.tci.Current.Value
                self.wt1 = tci
                self.wt2.Update(time_index, float(self.wt1))
        
        self.Value = self.wt1

        return self.wt2
