'''
Transformations that primarily involve numerical computation on variables.
'''

import numpy as np
import pandas as pd
from bids.utils import listify
from .base import Transformation
from bids.analysis import hrf
from bids.variables import SparseRunVariable


class Convolve(Transformation):
    """Convolve the input variable with an HRF.

    Args:
        var (Variable): The variable to convolve.
        model (str): The name of the HRF model to apply. Must be one of 'spm',
            'glover', or 'fir'.
        derivative (bool): Whether or not to include the temporal derivative.
        dispersion (bool): Whether or not to include the dispersion derivative.
        fir_delays (iterable): A list or iterable of delays to use if model is
            'fir' (ignored otherwise). Spacing between delays must be fixed.

    Note: Uses the HRF convolution functions implemented in nistats.
    """

    _input_type = 'variable'

    def _transform(self, var, model='spm', derivative=False, dispersion=False,
                   fir_delays=None):

        model = model.lower()

        if isinstance(var, SparseRunVariable):
            sr = self.collection.sampling_rate
            var = var.to_dense(sr)

        df = var.to_df(entities=False)
        onsets = df['onset'].values
        vals = df[['onset', 'duration', 'amplitude']].values.T

        if model in ['spm', 'glover']:
            if derivative:
                model += ' + derivative'
            if dispersion:
                model += ' + dispersion'
        elif model != 'fir':
            raise ValueError("Model must be one of 'spm', 'glover', or 'fir'.")

        convolved = hrf.compute_regressor(vals, model, onsets,
                                          fir_delays=fir_delays, min_onset=0)

        return pd.DataFrame(convolved[0], index=df.index).squeeze()


class Demean(Transformation):

    def _transform(self, data):
        return data - data.mean()


class Orthogonalize(Transformation):

    _variables_used = ('variables', 'other')
    _densify = ('variables', 'other')
    _align = ('other')

    def _transform(self, var, other):

        other = listify(other)

        # Set up X matrix and slice into it based on target variable indices
        X = np.array([self._variables[c].values.values.squeeze()
                      for c in other]).T
        X = X[var.index, :]
        assert len(X) == len(var)
        y = var.values
        _aX = np.c_[np.ones(len(y)), X]
        coefs, resids, rank, s = np.linalg.lstsq(_aX, y)
        result = pd.DataFrame(y - X.dot(coefs[1:]), index=var.index)
        return result


class Product(Transformation):

    _loopable = False
    _groupable = False
    _align = True
    _output_required = True

    def _transform(self, data):
        data = pd.concat(data, axis=1)
        return data.product(1)


class Scale(Transformation):
    ''' Scale a variable.

    Args:
        data (Series/DF): The variables to scale.
        demean (bool): If True, demean each column.
        rescale (bool): If True, divide variables by their standard deviation.
        replace_na (str): Whether/when to replace missing values with 0. If
            None, no replacement is performed. If 'before', missing values are
            replaced with 0's before scaling. If 'after', missing values are
            replaced with 0 after scaling.

    '''

    def _transform(self, data, demean=True, rescale=True, replace_na=None):
        if replace_na == 'before':
            data = data.fillna(0.)
        if demean:
            data -= data.mean()
        if rescale:
            data /= data.std()
        if replace_na == 'after':
            data = data.fillna(0.)
        return data


class Sum(Transformation):

    _loopable = False
    _groupable = False
    _align = True
    _output_required = True

    def _transform(self, data, weights=None):
        data = pd.concat(data, axis=1)
        if weights is None:
            weights = np.ones(data.shape[1])
        else:
            weights = np.array(weights)
            if len(weights.ravel()) != data.shape[1]:
                raise ValueError("If weights are passed to sum(), the number "
                                 "of elements must equal number of variables"
                                 "being summed.")
        return (data * weights).sum(axis=1)



class Threshold(Transformation):
    ''' Threshold and/or binarize a variable.

    Args:
        data (Series/DF): The pandas structure to threshold.
        threshold (float): The value to binarize around (values above will
            be assigned 1, values below will be assigned 0).
        binarize (bool): If True, binarizes all non-zero values (i.e., every
            non-zero value will be set to 1).
        above (bool): Specifies which values to retain with respect to the
            cut-off. If True, all value above the threshold will be kept; if
            False, all values below the threshold will be kept. Defaults to
            True.
        signed (bool): Specifies whether to treat the threshold as signed
        (default) or unsigned. For example, when passing above=True and
        threshold=3, if signed=True, all and only values above +3 would be
        retained. If signed=False, all absolute values > 3 would be retained
        (i.e.,values in  the range -3 < X < 3 would be set to 0).

    '''

    _groupable = False

    def _transform(self, data, threshold=0., binarize=False, above=True,
                   signed=True):
        if not signed:
            threshold = np.abs(threshold)
            data = data.abs()
        keep = data >= threshold if above else data <= threshold
        data[~keep] = 0
        if binarize:
            data[keep] = 1
        return data


class And(Transformation):
    ''' Logical AND on two or more variables.

    Args:
        dfs (list of DFs): variables to enter into the conjunction.
    '''

    _loopable = False
    _groupable = False
    _output_required = True

    def _transform(self, dfs):
        df = pd.concat(dfs, axis=1)
        return df.all(axis=1).astype(int)


class Not(Transformation):
    ''' Logical negation of a variable.

    Args:
        var (Series): Variable to negate. Must be convertible to bool.
    '''

    _loopable = True
    _groupable = False

    def _transform(self, var):
        return ~var.astype(bool)


class Or(Transformation):
    ''' Logical OR (inclusive) on two or more variables.

    Args:
        dfs (list of DFs): variables to enter into the disjunction.
    '''

    _loopable = False
    _groupable = False
    _output_required = True

    def _transform(self, dfs):
        df = pd.concat(dfs, axis=1)
        return df.any(axis=1).astype(int)
