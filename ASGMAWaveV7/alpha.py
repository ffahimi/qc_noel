from AlgorithmImports import *
from indicators import *

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
            # algorithm.Log(f"------------------")
            # algorithm.Log(f"Checking conditions for symbol: {symbol} {symbol.Value}")
            # algorithm.Log(f"Invested={algorithm.Portfolio[symbol].Invested}, Quantity={algorithm.Portfolio[symbol].Quantity}")
            algorithm.Log("agap2," + str(symbolData.current_time)+ "," + str(symbolData.current_close) + "," + str(symbolData.wt.current_hlc3) + "," +str(symbolData.pso.mini)  + "," +str(symbolData.pso.maxi) + "," +str(symbolData.pso.val) + "," +str(symbolData.tpx.avgbulllma) + "," +str(symbolData.tpx.bulls) + "," +str(symbolData.tpx.avgbearlma) + "," +str(symbolData.tpx.net) + "," +str(symbolData.tpx.tpx))
            
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
                    # algorithm.Log(f"Insight {newDirection} for {symbol.Value}")
                    # Generate insight only if not invested or if wanting to trade in opposite direction
                    insight = Insight.Price(symbol, timedelta(days=1), newDirection, None, None, None, 0.6)
                    insights.append(insight)
                    self.symbol_directions[symbol] = newDirection  # Update the direction for this symbol
                # else:
                    # algorithm.Log(f"Not invested or opposite, so not doing anything.")
        
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
        self.tpx = RedKTPX(algorithm)
        self.pso = PSO(algorithm)

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
        self.tpx.Update(consolidated.Time, consolidated.High, consolidated.Low, consolidated.Close)
        self.pso.Update(consolidated.Time, consolidated.High, consolidated.Low, consolidated.Close)
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
