from dataclasses import dataclass, field
import pyomo.environ as po

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
    co2_limit : float
        Maximum CO2 equivalent emission limit.
    ch4_equivalent : float
        Factor for calculating the CO2 equivalent of CH4 emissions. If not
        supplied, the global-warming potential (GWP) of 25 is used. Source e.g.
        https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Glossary:Carbon_dioxide_equivalent
        Default: 25
    n2o_equivalent : float
        Factor for calculating the CO2 equivalent of N2O emissions. If not
        supplied, the global-warming potential (GWP) of 298 is used. Source:
        https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Glossary:Carbon_dioxide_equivalent
        Default: 298
    commodities : dict
        Contains key-value-pair of the CO2, CH4, N2O and negative CO2 emission
        commodities to be considered in the emission constraint and their
        respective output bus labels in a list. Note: output buses are
        considered.
        Naming convention: allowed keys are "co2_commodities",
        "ch4_commodities", "n2o_commodities", "negative_co2_commodities".

    """
    type: str
    co2_limit: float
    ch4_equivalent: float = 25
    n2o_equivalent: float = 298
    commodities: dict = field(default_factory=dict)

    def build_constraint(self, model):
        """Pass constraint to the model"""
        # check if there are output flows corresponding to commodities
        flows = {"co2_commodities": 0, "ch4_commodities": 0,
                 "n2o_commodities": 0, "negative_co2_commodities": 0}
        for i, o in model.flows:
            for commodity in self.commodities:
                if o.label in self.commodities[commodity]:
                    flows[commodity] += sum(model.flow[i, o, :, :])

        def co2_emission_rule(model):
            expr = (
                flows["co2_commodities"] +
                flows["ch4_commodities"] * self.ch4_equivalent +
                flows["n2o_commodities"] * self.n2o_equivalent -
                flows["negative_co2_commodities"]
            )
            return expr <= self.co2_limit

        setattr(model, "co2_emission_limit",
                po.Constraint(rule=co2_emission_rule))


CONSTRAINT_TYPE_MAP = {"co2_emission_limit": CO2EmissionLimit}
