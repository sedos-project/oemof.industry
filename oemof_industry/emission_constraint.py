from dataclasses import dataclass, field

import pyomo.environ as po
from oemof.tabular.constraint_facades import ConstraintFacade

@dataclass
class CO2EmissionLimit(ConstraintFacade):
    name: str
    type: str
    co2_limit: float
    ch4_equivalent: float
    n2o_equivalent: float
    co2_commodities: list = field(default_factory=list)
    ch4_commodities: list = field(default_factory=list)
    n2o_commodities: list = field(default_factory=list)
    negative_co2_commodities: list = field(default_factory=list)

    def build_constraint(self, model):
        # to use the constraints in oemof.solph, we need to pass the model.

        # check if there are flows corresponding to commodities
        co2_flows, ch4_flows, n2o_flows = 0, 0, 0
        neg_co2_flows = 0
        for i, o in model.flows:
            if o.label in self.co2_commodities:
                co2_flows += sum(model.flow[i, o, :, :])
            if o.label in self.ch4_commodities:
                ch4_flows += sum(model.flow[i, o, :, :])
            if o.label in self.n2o_commodities:
                n2o_flows += sum(model.flow[i, o, :, :])
            elif o.label in self.negative_co2_commodities:
                neg_co2_flows += sum(model.flow[i, o, :, :])

        def co2_emission_rule(model):
            expr = (
                co2_flows +
                ch4_flows * self.ch4_equivalent +
                n2o_flows * self.n2o_equivalent - neg_co2_flows
            )
            return expr >= self.co2_limit

        model.co2_emission_limit = po.Constraint(
            rule=co2_emission_rule
        )


CONSTRAINT_TYPE_MAP = {"co2_emission_limit": CO2EmissionLimit}
