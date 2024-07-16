from dataclasses import dataclass, field
import pyomo.environ as po

from oemof.tabular.constraint_facades import ConstraintFacade

@dataclass
class CO2EmissionLimit(ConstraintFacade):
    type: str
    co2_limit: float
    ch4_equivalent: float = 25
    n2o_equivalent: float = 298
    commodities: dict = field(default_factory=dict)

    def build_constraint(self, model):
        # to use the constraints in oemof.solph, we need to pass the model.

        # check if there are flows corresponding to commodities
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
