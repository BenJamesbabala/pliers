''' Base Extractor class and associated functionality. '''

from collections import defaultdict
from abc import ABCMeta, abstractmethod
from six import with_metaclass
import pandas as pd
import numpy as np
from pliers.transformers import Transformer
from pliers.utils import isgenerator


class Extractor(with_metaclass(ABCMeta, Transformer)):

    ''' Base class for Converters.'''

    def __init__(self):
        super(Extractor, self).__init__()

    def transform(self, stim, *args, **kwargs):
        result = super(Extractor, self).transform(stim, *args, **kwargs)
        return list(result) if isgenerator(result) else result

    @abstractmethod
    def _extract(self, stim):
        pass

    def _transform(self, stim, *args, **kwargs):
        return self._extract(stim, *args, **kwargs)

    def plot(self, result, stim=None):
        raise NotImplementedError("No plotting method is defined for class "
                                  "%s." % self.__class__.__name__)


class ExtractorResult(object):

    def __init__(self, data, stim, extractor, features=None, onsets=None,
                 durations=None):
        self.data = data
        self.extractor = extractor
        self.features = features
        self._history = None

        # Some Extractors pass a list of Stims for various reasons
        if isinstance(stim, (list, tuple)):
            if not len(set(stim)) == 1:
                raise ValueError("Multiple Stim instances passed to the 'stim'"
                                 " argument in ExtractorResult initialization;"
                                 " each ExtractorResult can only be associated"
                                 " with a single Stim.")
            stim = stim[0]
        self.stim = stim

        if onsets is None:
            onsets = stim.onset
        self.onsets = onsets if onsets is not None else np.nan

        if durations is None:
            durations = stim.duration
        self.durations = durations if durations is not None else np.nan

    def to_df(self, stim_name=False):
        df = pd.DataFrame(self.data)
        if self.features is not None:
            df.columns = self.features
        df.insert(0, 'duration', self.durations)
        df.insert(0, 'onset', self.onsets)
        if stim_name:
            df['stim_name'] = self.stim.name
        return df

    @property
    def history(self):
        return self._history

    @history.setter
    def history(self, history):
        self._history = history

    @classmethod
    def merge_features(cls, results, extractor_names=True, stim_names=True,
                       source_files=True, flatten_columns=False):
        ''' Merge a list of ExtractorResults bound to the same Stim into a
        single DataFrame.

        Args:
            results (list, tuple): A list of ExtractorResult instances to merge
            extractor_names (bool): if True, stores the associated Extractor
                names in the top level of the column MultiIndex.
            stim_names (bool): if True, stores the associated Stim names in the
                top level of the row MultiIndex.
            source_files (bool): if True, stores the full path of the stimuli
                on disk in a new column.
            flatten_columns (bool): if True, flattens the resultant column
                MultiIndex such that feature columns are in the format
                <extractor class>_<feature name>
        '''

        # Make sure all ExtractorResults are associated with same Stim.
        stims = set([r.stim.name for r in results])
        dfs = [r.to_df() for r in results]
        if len(stims) > 1:
            raise ValueError("merge_features() can only be called on a set of "
                             "ExtractorResults associated with the same Stim.")

        keys = [r.extractor.name for r in results] if extractor_names else None

        # If onsets are all NaN
        if all([r['onset'].isnull().all() for r in dfs]):
            if len(set([len(r) for r in dfs])) > 1:
                raise ValueError("If ExtractorResults do not specify onsets, "
                                 "all ExtractorResults to merge must have "
                                 "identical numbers of rows.")
            dfs = [r.drop(['onset'], axis=1) for r in dfs]
            result = pd.concat(dfs, axis=1, keys=keys)
            result.insert(0, 'onset', np.nan)

        # If onsets are specified
        elif all([r['onset'].notnull().all() for r in dfs]):
            dfs = [r.set_index('onset').sort_index() for r in dfs]
            result = pd.concat(dfs, axis=1, keys=keys).reset_index()

        else:
            raise ValueError("To merge a list of ExtractorResults, all "
                             "instances must either contain onsets, or lack "
                             "onsets and have the same number of rows. It is "
                             "not possible to merge mismatched instances.")

        result = result.drop('duration', axis=1, level=1)
        result.columns = pd.MultiIndex.from_tuples(result.columns.values)
        result.insert(0, 'duration', results[0].durations)

        result.insert(0, 'class', results[0].stim.__class__.__name__)
        result.insert(0, 'filename', results[0].stim.filename)
        result.insert(0, 'history', str(results[0].stim.history))

        if stim_names:
            result.insert(0, 'stim_name', list(stims)[0])

        if source_files:
            result.insert(0, 'source_file', results[0].history.to_df().iloc[0].source_file)

        result = result.sort_values(['onset']).reset_index(drop=True)
        if flatten_columns:
            result.columns = ['_'.join(str(lvl) for lvl in col).strip('_') for col in result.columns.values]
        return result

    @classmethod
    def merge_stims(cls, results):
        results = [r.to_df(True) if isinstance(
            r, ExtractorResult) else r for r in results]
        return pd.concat(results, axis=0).sort_values('onset').reset_index(drop=True)


def merge_results(results, **merge_feature_args):
    ''' Merges a list of ExtractorResults instances and returns a pandas DF.
    Args:
        results (list, tuple): A list of ExtractorResult instances to merge.
        merge_feature_args (kwargs): Additional argument settings to use
            when merging across features.

    Returns: a pandas DataFrame with features concatenated along the column
        axis and stims concatenated along the row axis.
    '''

    stims = defaultdict(list)

    for r in results:
        stims[hash(r.stim)].append(r)

    # First concatenate all features separately for each Stim
    for k, v in stims.items():
        stims[k] = ExtractorResult.merge_features(v, **merge_feature_args)

    # Now concatenate all Stims
    stims = list(stims.values())
    return stims[0] if len(stims) == 1 else \
        ExtractorResult.merge_stims(stims)
