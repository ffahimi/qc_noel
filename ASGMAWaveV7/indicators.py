from AlgorithmImports import *
from collections import deque
from QuantConnect.Indicators import *
from symbol_data import *
import math, numpy as np
import pandas

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


class RedKTPX(PythonIndicator):
    
    def __init__(self, algorithm):

        self.algorithm = algorithm
        self.length = 7
        self.smooth = 3
        self.clevel = 30
        self.pre_s = False
        self.pre_sv = 3
        self.high = deque(maxlen=(2))
        self.low = deque(maxlen=(2))
        self.avgbulllma = LinearWeightedMovingAverage(self.length)
        self.avgbearlma = LinearWeightedMovingAverage(self.length)
        self.avgbullslma = LinearWeightedMovingAverage(self.pre_sv)
        self.avgbearslma = LinearWeightedMovingAverage(self.pre_sv)
        self.tpx = LinearWeightedMovingAverage(self.smooth)
        self.avgbears = 0
        self.avgbulls = 0
        self.net = 0

    def Update(self, time_index, high, low, close) -> bool:

        self.high.append(high)
        self.low.append(low)
        high_2_arr = np.array(self.high)
        low_2_arr = np.array(self.low)

        if len(high_2_arr) == 2 and len(low_2_arr) == 2:

            R = np.max(np.array(self.high)) - np.min(np.array(self.low))   
            
            # TODO: Check  
            hiup = 0 if high_2_arr[1]-high_2_arr[0] < 0 else high_2_arr[1]-high_2_arr[0]
            loup = 0 if low_2_arr[1]-low_2_arr[0] < 0 else low_2_arr[1]-low_2_arr[0]
            bulls = min((hiup + loup)/R, 1) *100

            
            if not math.isnan(bulls):
                self.avgbulllma.Update(time_index, bulls)
            
            if self.avgbulllma.IsReady:
                self.avgbullslma.Update(time_index, self.avgbulllma.Current.Value)

            if self.avgbullslma.IsReady and self.avgbulllma.IsReady:
                if self.pre_s:
                    self.avgbulls = self.avgbullslma.Current.value
                else:
                    self.avgbulls = self.avgbulllma.Current.Value
        
            hidn = 0 if high_2_arr[1] - high_2_arr[0] > 0 else high_2_arr[1] - high_2_arr[0]
            lodn = 0 if low_2_arr[1] - low_2_arr[0] > 0 else low_2_arr[1] - low_2_arr[0]
            bears = max((hidn + lodn)/R , -1) * 100
            
            if not math.isnan(bears):
                self.avgbearlma.Update(time_index, bears)
            
            if self.avgbearlma.IsReady:
                self.avgbearslma.Update(time_index, self.avgbearlma.Current.Value)

            if self.avgbearslma.IsReady and self.avgbearlma.IsReady:
                if self.pre_s:
                    self.avgbears = self.avgbearslma.Current.value
                else:
                    self.avgbears = self.avgbearlma.Current.Value

            if self.avgbearslma.IsReady and self.avgbearlma.IsReady and self.avgbullslma.IsReady and self.avgbulllma.IsReady:
                self.net = self.avgbulls - self.avgbears
                self.tpx.Update(time_index, self.net)

            return self.tpx.IsReady


class PSO(PythonIndicator):
    
    # The alma indicator with percentage change of close as the input
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.period =  32
        self.smooth_period = 5
        self.level1 = 0.9
        self.level2 = 0.2
        self.ema0_current = 0.0
        self.ema1_current = 0.0
        self.val = 0.0
        self.min_level = 0.0
        self.max_level = 0.0
        
        self.high = deque(maxlen=(self.period))
        self.low = deque(maxlen=(self.period))
        self.ema0 = deque(maxlen=(2))
        self.ema1 = deque(maxlen=(2))

        self.val = 0

    def Update(self, time_index, high, low, close) -> bool:

        
        self.high.append(high)
        self.low.append(low)

        high32_arr = np.array(self.high)
        low32_arr = np.array(self.low)

        self.algorithm.Log(str(high32_arr))
        if (len(high32_arr) == self.period) and (len(low32_arr) == self.period):
            alpha = 2.0/(1 + self.smooth_period)
            self.min_level = min(self.level1, self.level2)
            self.max_level = max(self.level1, self.level2)
            mini = np.min(low32_arr)
            maxi = np.max(high32_arr)
            sto = 10.0*((close - mini)/(maxi - mini)-0.5)
            
            ema0_arr = np.array(self.ema0)
            ema1_arr = np.array(self.ema1)

            self.algorithm.Log(str(ema0_arr) + "...." + str(ema1_arr)) 

            # before pushing the current value for ema0
            if len(ema0_arr) >= 1 and len(ema1_arr) >= 1:
                self.ema0_current = self.ema0_current + alpha*(sto - self.ema0_current)
                self.ema0.append(self.ema0_current)
                # CHECK: is ema0[1] and ema1[0] actually mean their previous value 
                self.ema1_current = ema1_arr[0] + alpha*(self.ema0_current - self.ema1_current)
                self.ema1.append(self.ema1_current)
                # CHECK: is this supposed to be the exponential of the last value 
                iexp = math.exp(self.ema1_curent)

                self.val = (iexp - 1.0)/(iexp + 1.0)

        return 1
