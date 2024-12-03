from dataclasses import dataclass, field
import pyomo.environ as po
import json

from oemof.tabular.constraint_facades import ConstraintFacade

@dataclass
class CO2EmissionLimit(ConstraintFacade):
    """
    Implements a CO2 equivalent emission constraint.

    The emissions can be based on one or more of the following:
    CO2, CH4, N2O, negative CO2 emissions

    Note that the constraint is based on output flows, see parameter
    description of `commodities` for more information.

    The following constraint is added to the model:

    .. math::
        CO_{2}\_\text{limit} \geq \sum_{f} \sum_{t} \left( CO_{2_{f, t}} + CH_{4_{f, t}} \cdot CH_{4}\_\text{factor} + N_{2}O_{f, t} \cdot N_{2}O\_\text{factor} - \text{negative}\_CO_{2_{f, t}} \right)

    Parameters
    ----------
    type : str
        Needs to be "co2_emission_limit" according to `CONSTRAINT_TYPE_MAP`
    co2_limit : float or list
        Maximum CO2 equivalent emission limit. In case of a list the constraint
        is added for each period separately.
    ch4_factor : float
        Factor for calculating the CO2 equivalent of CH4 emissions. If not
        supplied, the global-warming potential (GWP) of 28 is used, according
        to IPCC AR5 https://www.ipcc.ch/site/assets/uploads/2018/02/WG1AR5_Chapter08_FINAL.pdf
        Default: 28
    n2o_factor : float
        Factor for calculating the CO2 equivalent of N2O emissions. If not
        supplied, the global-warming potential (GWP) of 265 is used, according
        to IPCC AR5 https://www.ipcc.ch/site/assets/uploads/2018/02/WG1AR5_Chapter08_FINAL.pdf
        Default: 265
    commodities : dict
        Contains key-value-pair of the CO2, CH4, N2O and negative CO2 emission
        commodities to be considered in the emission constraint and their
        respective output bus labels in a list. Note: output buses are
        considered.
        Naming convention: allowed keys are "co2_commodities",
        "ch4_commodities", "n2o_commodities", "negative_co2_commodities".

    Examples
    --------
    >>> import pandas as pd
    >>> from oemof.solph import EnergySystem, Model, processing
    >>> from oemof.solph.flows import Flow
    >>> from oemof.solph.components import Source, Sink
    >>> from oemof.solph.buses import Bus
    >>> from oemof_industry.mimo_converter import MultiInputMultiOutputConverter
    >>> from oemof_industry.emission_constraint import CO2EmissionLimit

    >>> idx = pd.date_range("1/1/2017", periods=2, freq="H")
    >>> es = EnergySystem(timeindex=idx)

    >>> # Buses
    >>> b_gas = Bus(label="gas", balanced=False)
    >>> b_hydro = Bus(label="hydro", balanced=False)
    >>> b_electricity = Bus(label="electricity")
    >>> b_co2 = Bus(label="co2", balanced=False)
    >>> b_ch4 = Bus(label="ch4", balanced=False)

    >>> # Components
    >>> load_el = Sink(
    ...        label="demand",
    ...        inputs={b_electricity: Flow(fix=[100, 100], nominal_value=1)})
    >>> mimo = MultiInputMultiOutputConverter(
    ...    label="mimo",
    ...    inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
    ...    outputs={
    ...        b_electricity: Flow(),
    ...        b_co2: Flow(),
    ...        b_ch4: Flow(),
    ...    },
    ...    emission_factors={
    ...        b_co2: {b_gas: 0.8, b_hydro: 0.6},
    ...        b_ch4: {b_gas: 0.4, b_hydro: 0.2},
    ...    },
    ...    conversion_factors={b_gas: 1.2, b_hydro: 1.3})

    >>> # Emission constraint
    >>> emission_constraint = CO2EmissionLimit(
    ...    type="co2_emission_limit",
    ...    co2_limit=10000,
    ...    ch4_factor=28,
    ...    n2o_factor=265,
    ...    commodities={"co2_commodities": ["co2"],
    ...                 "ch4_commodities": ["ch4"]})

    >>> es.add(b_gas, b_hydro, b_electricity, load_el, b_co2, b_ch4, mimo)

    >>> # create an optimization problem
    >>> om = Model(es)

    >>> # Build emission constraint
    >>> emission_constraint.build_constraint(om)

    >>> print(om.co2_emission_limit.expr)
    flow[mimo, co2, 0, 0] + flow[mimo, co2, 0, 1] + (flow[mimo, ch4, 0, 0] + flow[mimo, ch4, 0, 1]) * 25 <= 10000

    """
    type: str
    co2_limit: float
    ch4_factor: float = 258
    n2o_factor: float = 265
    commodities: dict = field(default_factory=dict)

    def build_constraint(self, model):
        """Pass constraint to the model"""

        def co2_emission_rule(model):
            """constraint rule"""
            expr = (
                    flows["co2_commodities"] +
                    flows["ch4_commodities"] * self.ch4_factor +
                    flows["n2o_commodities"] * self.n2o_factor -
                    flows["negative_co2_commodities"]
            )
            if isinstance(self.co2_limit, list):
                return expr <= self.co2_limit[p]
            elif isinstance(self.co2_limit, float) or isinstance(self.co2_limit, int):
                return expr <= self.co2_limit
            else:
                raise TypeError(f"co2 limit should be list, float or int but "
                                f"is {type(self.co2_limit)}.")

        if not isinstance(self.commodities, dict):
            # load commodities as dict
            self.commodities = json.loads(self.commodities.replace("#", '"'))

        # check if there are output flows corresponding to commodities
        p_counter = None
        for p, t in model.TIMEINDEX:
            if p != p_counter:  # to save for-loops flows are added as sum over all t
                flows = {"co2_commodities": 0, "ch4_commodities": 0,
                         "n2o_commodities": 0, "negative_co2_commodities": 0}
                for i, o in model.flows:
                    for commodity in self.commodities:
                        if o.label in self.commodities[commodity]:
                            flows[commodity] += sum(model.flow[i, o, p, :])

                p_counter = p

                setattr(model, f"co2_emission_limit_{p}",
                        po.Constraint(rule=co2_emission_rule))


CONSTRAINT_TYPE_MAP = {"co2_emission_limit": CO2EmissionLimit}
