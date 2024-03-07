from AlgorithmImports import *
import numpy as np

class ASGMAIndicator:
    def __init__(self, algorithm, symbol, length1=25, offset=0.85, sigma1=6, length=14, volatilityPeriod=20):
        self.algorithm = algorithm
        self.symbol = symbol
        self.length1 = length1
        self.offset = offset
        self.sigma1 = sigma1
        self.length = length
        self.volatilityPeriod = volatilityPeriod
        
        self.priceHistory = []
        self.avpchangeSeries = []
        self.gmaValues = []
        self.std = self.algorithm.STD(symbol, volatilityPeriod, Resolution.Minute)
        self.previous_avpchange = None
        self.previous_gma = None

    def Update(self, time, price):
        if len(self.priceHistory) >= 1:
            pchange = (price - self.priceHistory[-1]) / self.priceHistory[-1] * 100 if self.priceHistory[-1] != 0 else 0
        else:
            pchange = 0
        self.priceHistory.append(price)
        
        if len(self.priceHistory) >= self.length1:
            alma_values = self.priceHistory[-self.length1:]
            avpchange = self.calculate_alma(alma_values, self.length1, self.offset, self.sigma1)
            self.avpchangeSeries.append(avpchange)
            
            if len(self.avpchangeSeries) >= self.length:
                sigma = self.std.Current.Value if self.std.IsReady else 1.0
                gma = self.calculate_gma(self.avpchangeSeries, self.length, sigma)
                self.gmaValues.append(gma)
                
                # Determine signals based on the crossover and crossunder
                buySignal = self.previous_avpchange is not None and self.previous_avpchange < self.previous_gma and avpchange >= gma
                sellSignal = self.previous_avpchange is not None and self.previous_avpchange > self.previous_gma and avpchange <= gma
                
                # Update previous values for the next comparison
                self.previous_avpchange = avpchange
                self.previous_gma = gma
                
                return buySignal, sellSignal
        return False, False

    def calculate_alma(self, series, length, offset, sigma):
        m = offset * (length - 1)
        s = length / sigma
        weights = np.exp(-np.power(np.arange(length) - m, 2) / (2 * s * s))
        weighted_sum = np.dot(weights, series[-length:])
        return weighted_sum / np.sum(weights)

    def calculate_gma(self, series, length, sigma):
        gma = 0.0
        sum_of_weights = 0.0
        for i in range(length):
            weight = np.exp(-np.power(i - (length - 1), 2) / (2 * sigma ** 2))
            gma += series[-i - 1] * weight
            sum_of_weights += weight
        return gma / sum_of_weights

class ASGMAAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2023, 1, 1)
        # self.SetEndDate(2023, 12, 30)
        self.SetCash(100000)
        
        self.symbol = self.AddEquity("SPY", Resolution.Minute).Symbol
        self.asgma = ASGMAIndicator(self, self.symbol, length1=25, offset=0.85, sigma1=6, length=14, volatilityPeriod=20)

    def OnData(self, data):
        if self.symbol in data and data[self.symbol] is not None:
            price = data[self.symbol].Close
            buySignal, sellSignal = self.asgma.Update(self.Time, price)
            
            if buySignal and not self.Portfolio[self.symbol].Invested:
                self.SetHoldings(self.symbol, 1)
                self.Log(f"Buy SPY at {price}")
            elif sellSignal and self.Portfolio[self.symbol].Invested:
                self.Liquidate(self.symbol)
                self.Log(f"Sell SPY at {price}")
        else:
            # This log is optional, to inform you whenever data for 'self.symbol' is missing
            self.Log(f"No data for {self.symbol} at {self.Time}")               
