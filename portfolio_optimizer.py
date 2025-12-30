import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from scipy.optimize import curve_fit, least_squares


class PortfolioOptimizer:
    def __init__(self, sine_fitter):
        self.sine_fitter = sine_fitter

    def cluster_by_phase(self, top_fits):
        """Cluster stocks by sine wave phase"""
        phases = np.array([[top_fits[tkr]['phase']] for tkr in top_fits])
        n_clusters = min(4, len(top_fits))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(phases)
        labels = kmeans.labels_

        groups = {i: [] for i in range(n_clusters)}
        for i, tkr in enumerate(top_fits):
            groups[labels[i]].append(tkr)

        return groups, n_clusters

    def calculate_initial_weights(self, groups, n_clusters):
        """Calculate equal weights per phase group"""
        weights = {}
        for phase, stocks in groups.items():
            w = (1.0 / n_clusters) / len(stocks) if stocks else 0
            for s in stocks:
                weights[s] = w
        return weights

    def residual_function(self, w_vec, weights, prices):
        """Residual function for optimization"""
        # Update weights with current values
        current_weights = dict(zip(weights.keys(), w_vec))
        port = (prices[list(current_weights.keys())] * pd.Series(current_weights)).sum(axis=1)
        logport = np.log(port.dropna())
        detrend_port = logport - logport.rolling(100).mean()
        y_port = detrend_port.dropna().values
        t_port = np.arange(len(y_port))
        popt_port, _ = curve_fit(self.sine_fitter.sine, t_port, y_port, p0=[0.1, 1/1260, 0, 0])
        yfit_port = self.sine_fitter.sine(t_port, *popt_port)
        return y_port - yfit_port

    def optimize_weights(self, top_fits, prices):
        """Optimize portfolio weights"""
        groups, n_clusters = self.cluster_by_phase(top_fits)
        weights = self.calculate_initial_weights(groups, n_clusters)

        w0 = np.array(list(weights.values()))
        res = least_squares(
            lambda w: self.residual_function(w, weights, prices),
            w0,
            bounds=(0, 1),
            method='trf'
        )
        opt_weights = dict(zip(weights.keys(), res.x / res.x.sum()))

        return opt_weights, res