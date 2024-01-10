import pathlib

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa
# from oemof.tabular.postprocessing import calculations
from oemof.tabular.facades import Bus, Commodity, Conversion, Excess, Load

from oemof_industry.mimo_converter import MIMO

MIMO_DATAPACKAGE = (
    pathlib.Path(__file__).parent / "datapackages" / "mimo" / "datapackage.json"
)

TYPEMAP = {
    "bus": Bus,
    "commodity": Commodity,
    "conversion": Conversion,
    "excess": Excess,
    "load": Load,
    "mimo": MIMO,
}


es = EnergySystem.from_datapackage(
    str(MIMO_DATAPACKAGE), attributemap={}, typemap=TYPEMAP
)

m = Model(es)

# if you want dual variables / shadow prices uncomment line below
# m.receive_duals()

# select solver 'gurobi', 'cplex', 'glpk' etc
m.solve("cbc")

es.params = processing.parameter_as_dict(es)
es.results = m.results()

# Not working due to MIMO Group Flows not filtered in postprocessing.
# As the pyomo tuples of those variables are holding node, group_name, period
# and timeindex and period and timeindex are not removed, like it is done for
# Flow Vars, this leads to an error
# (ValueError: Length of names must match number of levels in MultiIndex) in
# `Calculator` class in `oemof.tabular.postprocessing.core` when Multiindex is
# set from oemof_tuple.

# -> We have to adapt tabulars postprocessing in order to get rid of this error
# Maybe only in private branch, as this is caused by custom facade MIMO.

# postprocessed_results = calculations.run_postprocessing(es)
# postprocessed_results.to_csv("./results.csv")
