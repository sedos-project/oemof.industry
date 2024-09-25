# -*- coding: utf-8 -*-

"""
solph version of oemof.network.MultiInputMultiOutputConverter including
sets, variables, constraints and parts of the objective function
for MultiInputMultiOutputConverterBlock objects.

SPDX-FileCopyrightText: Uwe Krien <krien@uni-bremen.de>
SPDX-FileCopyrightText: Simon Hilpert
SPDX-FileCopyrightText: Cord Kaldemeyer
SPDX-FileCopyrightText: Patrik Schönfeldt
SPDX-FileCopyrightText: Stephan Günther
SPDX-FileCopyrightText: Birgit Schachler
SPDX-FileCopyrightText: jnnr
SPDX-FileCopyrightText: jmloenneberga
SPDX-FileCopyrightText: David Fuhrländer
SPDX-FileCopyrightText: Johannes Röder
SPDX-FileCopyrightText: Johannes Kochems
SPDX-FileCopyrightText: Hendrik Huyskens <hendrik.huyskens@rl-institut.de>

SPDX-License-Identifier: MIT

"""
import dataclasses
import operator
from functools import reduce
from typing import Dict, Iterable, Union

from oemof.network import Node
from oemof.solph._helpers import warn_if_missing_attribute
from oemof.solph._plumbing import sequence
from oemof.solph.buses import Bus
from oemof.solph.flows import Flow
from oemof.tabular._facade import Facade
from pyomo.core import BuildAction, Constraint
from pyomo.core.base.block import ScalarBlock
from pyomo.environ import NonNegativeReals, Set, Var

CONSTRAINT_TYPES = ("min", "max", "fix")


class MultiInputMultiOutputConverter(Node):
    """A linear ConverterBlock object with n inputs and n outputs.

    Node object that relates any number of inflow and outflows with
    conversion factors. Inputs and outputs must be given as dictinaries.

    Parameters
    ----------
    inputs : dict
        Dictionary with inflows. Keys must be the starting node(s) of the
        inflow(s).
    outputs : dict
        Dictionary with outflows. Keys must be the ending node(s) of the
        outflow(s).
    conversion_factors : dict
        Dictionary containing conversion factors for conversion of each flow.
        Keys must be the connected nodes (typically Buses).
        The dictionary values can either be a scalar or an iterable with
        individual conversion factors for each time step.
        Default: 1. If no conversion_factor is given for an in- or outflow, the
        conversion_factor is set to 1.
    emission_factors : dict
        Dictionary with emission outflows, holding a dict with contributing
        input nodes and related conversion factors.
    flow_shares : dict
        Contains dictionary with flow shares, see example below.
        Minimum/Maximum/Fixed share of flow commodity
        based upon the sum of individual flows defined by the commodity group.
        Keys must be connected input/output nodes (typically Buses).
        The dictionary values can either be a scalar or an iterable with
        individual flow shares for each time step. If no flow share is given
        for a flow, no share is set for this flow.
    activity_bounds : dict
        Dictionary containing activity bounds.
    custom_attributes :
    primary : str (optional)
        Defines primary bus as the bus holding an investment. If no bus is
        holding an investment, primary bus is set to None.

    Examples
    --------
    Defining a MIMO-converter:

    >>> from oemof.solph import EnergySytem, Source, Sink
    >>> import pandas as pd
    >>> idx = pd.date_range("1/1/2017", periods=6, freq="H")
    >>> es = EnergySystem(timeindex=idx)

    >>> b_gas = Bus(label="INDGAS_OTH")
    >>> gas_source = Source(label="gas_station", outputs={b_gas: Flow()})
    >>> b_hydro = Bus(label="INDHH2_OTH")
    >>> hydro_source = Source(label="hydro_station", outputs={b_hydro: Flow()})
    >>> b_heat = Bus(label="IFTHTH")
    >>> heat_demand = Sink(
    ...    label="heat_demand",
    ...    inputs={b_heat: Flow(fix=[66, 66, 66, 0, 0, 16], nominal_value=1)})

    >>> b_ch4 = Bus(label="INDCH4N", balanced=False)
    >>> b_co2 = Bus(label="INDCO2N", balanced=False)
    >>> b_n2o = Bus(label="INDN2ON", balanced=False)

    >>> es.add(b_gas,gas_source, b_hydro, hydro_source, b_heat, heat_demand,
    ...       b_ch4, b_co2, b_n2o)

    >>> es.add(
    ...    MultiInputMultiOutputConverter(
    ...        label="mimo",
    ...        inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
    ...        outputs={
    ...            b_heat: Flow(),
    ...            b_co2: Flow(),
    ...            b_ch4: Flow(),
    ...            b_n2o: Flow(),
    ...        },
    ...        emission_factors={
    ...            b_co2: {b_gas: 56},
    ...            b_ch4: {b_gas: 0.0012},
    ...            b_n2o: {b_gas: 0.0006},
    ...        },
    ...        conversion_factors={"in": 1 / 0.82},
    ...        flow_shares={"max": {b_hydro: [0, 0, 0, 0.5, 1, 1]}}))

    >>> es.groups["mimo"].input_flow_shares["fix"]
    {"<oemof.solph.buses._bus.Bus: 'INDHH2_OTH'>": [0, 0, 0, 0.5, 1, 1]}

    Notes
    -----
    The following sets, variables, constraints and objective parts are created
     * :py:class:`~oemof.solph.components.experimental._mimo_converter.
     MultiInputMultiOutputConverterBlock`
    """

    def __init__(
        self,
        label=None,
        inputs=None,
        outputs=None,
        conversion_factors=None,
        emission_factors=None,
        flow_shares=None,
        activity_bounds=None,
        custom_attributes=None,
        **kwargs,
    ):
        self.label = label

        if inputs is None:
            warn_if_missing_attribute(self, "inputs")
            inputs = {}
        if outputs is None:
            warn_if_missing_attribute(self, "outputs")
            outputs = {}

        self.emission_factors = self._init_group(emission_factors)
        emissions = {
            node: flow
            for node, flow in outputs.items()
            if node in self.emission_factors
        }

        self.input_groups = self._unify_groups(inputs, "in")
        self.output_groups = self._unify_groups(outputs, "out", exclude=emissions)

        inputs = reduce(operator.ior, self.input_groups.values(), {})
        # Add emissions to outputs (as they are excluded from output groups before)
        outputs = reduce(operator.ior, self.output_groups.values(), {}) | emissions

        # Primary bus is defined as the bus holding an investment.
        # If no bus is holding an investment, primary bus is set to None
        buses_holding_investment = [
            bus
            for bus, flow in (inputs | outputs).items()
            if flow.investment is not None
        ]
        if len(buses_holding_investment) > 1:
            raise ValueError("Only one investment allowed.")
        self.primary_bus = (
            buses_holding_investment[0] if len(buses_holding_investment) == 1 else None
        )

        if custom_attributes is None:
            custom_attributes = {}

        super().__init__(
            label=label,
            inputs=inputs,
            outputs=outputs,
            **custom_attributes,
        )

        self.conversion_factors = self._init_conversion_factors(conversion_factors)
        self._init_flow_shares(flow_shares, inputs, outputs)
        self._init_activity_bounds(activity_bounds)

    def _init_flow_shares(self, flow_shares, inputs, outputs):
        flow_shares = {} if flow_shares is None else flow_shares
        self._check_constraint_types(flow_shares)

        # Check if fix flow share is combined with min or max flow share
        if "fix" in flow_shares:
            for node in flow_shares["fix"]:
                if "min" in flow_shares and node in flow_shares["min"]:
                    raise ValueError(
                        "Cannot combine 'fix' and 'min' flow share for same " "node."
                    )
                if "max" in flow_shares and node in flow_shares["max"]:
                    raise ValueError(
                        "Cannot combine 'fix' and 'max' flow share for same " "node."
                    )

        flow_shares = self._init_group(flow_shares)
        self.input_flow_shares = {
            flow_type: {
                node: share for node, share in node_shares.items() if node in inputs
            }
            for flow_type, node_shares in flow_shares.items()
        }
        self.output_flow_shares = {
            flow_type: {
                node: share for node, share in node_shares.items() if node in outputs
            }
            for flow_type, node_shares in flow_shares.items()
        }

    def _init_conversion_factors(
        self, conversion_factors: Dict[Bus, Union[float, Iterable]]
    ) -> Dict[Bus, Iterable]:
        """
        Set up the conversion_factors for each connected node.

        Parameters
        ----------
        conversion_factors : Dict[Bus, Union[float, Iterable]]
            Conversion factors set up by the user.

        Returns
        -------
        Dict[Bus, Iterable]
            Conversion factors for each connected node.
            Defaults to sequence(1).
        """
        if conversion_factors is None:
            conversion_factors = {}
        conversion_factors = {k: sequence(v) for k, v in conversion_factors.items()}
        missing_conversion_factor_keys = (
            set(self.outputs)
            | set(self.inputs)
            | set(self.input_groups)
            | set(self.output_groups)
        ) - set(conversion_factors)
        for cf in missing_conversion_factor_keys:
            conversion_factors[cf] = sequence(1)
        return conversion_factors

    @staticmethod
    def _check_constraint_types(parameter):
        # Check for invalid constraint types
        invalid_constraint_types = set(parameter) - set(CONSTRAINT_TYPES)
        if invalid_constraint_types:
            raise ValueError(
                f"Invalid flow share or activity bound types found: {invalid_constraint_types}. "
                "Must be one of 'min', 'max' or 'fix'."
            )

    def _init_activity_bounds(self, activity_bounds):
        activity_bounds = {} if activity_bounds is None else activity_bounds

        self._check_constraint_types(activity_bounds)
        if "fix" in activity_bounds and ("min" in activity_bounds or "max" in activity_bounds):
            raise ValueError(
                "Invalid activity bounds found. Cannot set 'fix' in combination with 'min' or 'max'."
            )

        self.activity_bounds = {key: sequence(value) for key, value in activity_bounds.items()}

    @staticmethod
    def _init_group(
        groups: Dict[str, Dict[Bus, Union[float, Iterable]]]
    ) -> Dict[str, Dict[Bus, Iterable]]:
        """
        Init grouped factors. Set up empty dict, if group is not set.
        For each given factor, turn value into sequence if necessary.

        Parameters
        ----------
        groups : Dict[str, Dict[Bus, Union[float, Iterable]]]
            Dictionary of groups holding nodes and related factors

        Returns
        -------
        Dict[str, Dict[Bus, Iterable]]
            Group holding nodes and related factors as sequences
        """
        if groups is None:
            return {}

        return {
            group: {node: sequence(value) for node, value in shares.items()}
            for group, shares in groups.items()
        }

    @staticmethod
    def _unify_groups(
        flows: Union[Dict[Bus, Flow], Dict[str, Dict[Bus, Flow]]],
        direction: str,
        exclude: Iterable[str] = None,
    ) -> Dict[str, Dict[Bus, Flow]]:
        """
        Group all inputs and outputs if they are not grouped yet.

        Single bus-flow entities are grouped into a single group thereby.

        Parameters
        ----------
        flows : Union[Dict[Bus, Flow], Dict[str, Dict[Bus, Flow]]]
            Input or output flows. This can be one of:
            1. a dict of groups, containing buses with related flows
            2. a dict of buses and related flows (as in default converter)
            3. a mix of option 1 and 2
        direction : str
            To differentiate between input and output flows.
        exclude: Iterable[str]
            List of nodes to exclude from grouping
            (needed to exclude emission buses from grouping)

        Returns
        -------
        dict
            Grouped input or output flows (as in option 1)
        """
        group_dict = {}
        group_counter = 0
        for key, flow in flows.items():
            if exclude and key in exclude:
                continue
            if isinstance(key, Bus):
                new_group = f"{direction}_group_{group_counter}"
                group_dict[new_group] = {key: flow}
                group_counter += 1
            else:
                group_dict[key] = flow
        return group_dict

    @staticmethod
    def constraint_group():
        return MultiInputMultiOutputConverterBlock


class MultiInputMultiOutputConverterBlock(ScalarBlock):
    r"""Block for the linear relation of nodes with type
    :class:`~oemof.industry.mimo_converter.MultiInputMultiOutputConverterBlock`

    **The following sets are created:** (-> see basic sets at
    :class:`.Model` )

    MIMOS
        A set with all
        :class:`~oemof.industry.mimo_converter.MultiInputMultiOutputConverter`
        objects.

    **The following constraints are created:**

    Linear relation :attr:`om.MultiInputMultiOutputConverterBlock.relation[i,o,t]`

    todo adapt:

        .. math::
            P_{i}(p, t) \cdot \eta_{o}(t) =
            P_{o}(p, t) \cdot \eta_{i}(t), \\
            \forall p, t \in \textrm{TIMEINDEX}, \\
            \forall n \in \textrm{CONVERTERS}, \\
            \forall i \in \textrm{INPUTS}, \\
            \forall o \in \textrm{OUTPUTS}

    While INPUTS is the set of Bus objects connected with the input of the
    Transformer and OUPUTS the set of Bus objects connected with the output of
    the Transformer. The constraint above will be created for all combinations
    of INPUTS and OUTPUTS for all TIMESTEPS. A Transformer with two inflows and
    two outflows for one day with an hourly resolution will lead to 96
    constraints.

    The index :math: n is the index for the Transformer node itself. Therefore,
    a `flow[i, n, p, t]` is a flow from the Bus i to the Transformer n at
    time index p, t.

    ======================  ============================  ====================
    symbol                  attribute                     explanation
    ======================  ============================  ====================
    :math:`P_{i,n}(p, t)`   `flow[i, n, p, t]`            Converter, inflow

    :math:`P_{n,o}(p, t)`   `flow[n, o, p, t]`            Converter, outflow

    :math:`\eta_{i}(t)`     `conversion_factor[i, n, t]`  Inflow, efficiency

    :math:`\eta_{o}(t)`     `conversion_factor[n, o, t]`  Outflow, efficiency

    ======================  ============================  ====================

    """

    CONSTRAINT_GROUP = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _create(self, group=None):
        """Creates the linear constraint for the
        class:`MultiInputMultiOutputConverterBlock` block.
        """
        if group is None:
            return None

        m = self.parent_block()

        self.INPUT_GROUPS = Set(
            initialize=[(n, g) for n in group for g in n.input_groups], dimen=2
        )
        self.OUTPUT_GROUPS = Set(
            initialize=[(n, g) for n in group for g in n.output_groups],
            dimen=2,
        )

        self.INPUT_GROUP_FLOW = Var(
            self.INPUT_GROUPS,
            m.TIMEINDEX,
            within=NonNegativeReals,
        )
        self.OUTPUT_GROUP_FLOW = Var(
            self.OUTPUT_GROUPS, m.TIMEINDEX, within=NonNegativeReals
        )

        def _input_group_relation(block, n, g, p, t):
            lhs = sum(
                m.flow[i, n, p, t] / n.conversion_factors[i][t]
                for i in n.input_groups[g]
            )
            rhs = block.INPUT_GROUP_FLOW[n, g, p, t]
            return lhs == rhs

        self.input_relation = Constraint(
            [
                (n, g, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for g in n.input_groups
            ],
            rule=_input_group_relation,
        )

        def _output_group_relation(block, n, g, p, t):
            lhs = block.OUTPUT_GROUP_FLOW[n, g, p, t]
            rhs = sum(
                m.flow[n, o, p, t] / n.conversion_factors[o][t]
                for o in n.output_groups[g]
            )
            return lhs == rhs

        self.output_relation = Constraint(
            [
                (n, g, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for g in n.output_groups
            ],
            rule=_output_group_relation,
        )

        self.maximum_input_output_relation = Constraint(
            [
                (n, g, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for g in list(n.input_groups) + list(n.output_groups)
            ],
            noruleinit=True,
        )

        def _maximum_input_output_group_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    if n.primary_bus is None:
                        continue
                    if n.primary_bus in n.inputs:
                        g = list(n.input_groups)[0]
                        lhs = block.INPUT_GROUP_FLOW[n, g, p, t]
                        try:
                            rhs = m.InvestmentFlowBlock.total[n.primary_bus, n, p]
                        except (AttributeError, KeyError):
                            continue
                    else:
                        g = list(n.output_groups)[0]
                        lhs = block.OUTPUT_GROUP_FLOW[n, g, p, t]
                        try:
                            rhs = m.InvestmentFlowBlock.total[n, n.primary_bus, p]
                        except (AttributeError, KeyError):
                            # AttributeError is thrown in case of no InvestmentFlowBlock in whole ES,
                            # KeyError is thrown if primary flow has no investment
                            continue
                    block.maximum_input_output_relation.add((n, g, p, t), lhs <= rhs)

        self.maximum_input_output_relation_build = BuildAction(
            rule=_maximum_input_output_group_relation
        )

        self.input_output_group_relation = Constraint(
            [
                (n, g, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for g in list(n.input_groups) + list(n.output_groups)
            ],
            noruleinit=True,
        )

        def _input_output_group_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    # Connect input groups
                    for i, ii in zip(
                        list(n.input_groups)[:-1], list(n.input_groups)[1:]
                    ):
                        block.input_output_group_relation.add(
                            (n, i, p, t),
                            (
                                block.INPUT_GROUP_FLOW[n, i, p, t]
                                / n.conversion_factors[i][t]
                                == block.INPUT_GROUP_FLOW[n, ii, p, t]
                                / n.conversion_factors[ii][t]
                            ),
                        )
                    # Connect output groups
                    for o, oo in zip(
                        list(n.output_groups)[:-1], list(n.output_groups)[1:]
                    ):
                        block.input_output_group_relation.add(
                            (n, o, p, t),
                            (
                                block.OUTPUT_GROUP_FLOW[n, o, p, t]
                                / n.conversion_factors[o][t]
                                == block.OUTPUT_GROUP_FLOW[n, oo, p, t]
                                / n.conversion_factors[oo][t]
                            ),
                        )
                    # Connect input with output group:
                    # Use last input item as index
                    last_input = list(n.input_groups)[-1]
                    last_output = list(n.output_groups)[-1]
                    block.input_output_group_relation.add(
                        (n, last_input, p, t),
                        (
                            block.INPUT_GROUP_FLOW[n, last_input, p, t]
                            / n.conversion_factors[last_input][t]
                            == block.OUTPUT_GROUP_FLOW[n, last_output, p, t]
                            / n.conversion_factors[last_output][t]
                        ),
                    )

        self.input_output_group_relation_build = BuildAction(
            rule=_input_output_group_relation
        )

        def _get_operator_from_constraint_type(constraint_type):
            if constraint_type == "min":
                return operator.ge
            if constraint_type == "max":
                return operator.le
            if constraint_type == "fix":
                return operator.eq
            raise ValueError(f"Unknown constraint type: {constraint_type}")

        self.input_flow_share_relation = Constraint(
            [
                (n, i, c, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for i in n.inputs
                for c in CONSTRAINT_TYPES
            ],
            noruleinit=True,
        )

        def _input_flow_share_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    for flow_share_type, shares in n.input_flow_shares.items():
                        op = _get_operator_from_constraint_type(flow_share_type)
                        for i, flow_share in shares.items():
                            # Find related input group for given input node:
                            g = next(
                                g for g, inputs in n.input_groups.items() if i in inputs
                            )
                            lhs = m.flow[i, n, p, t] / n.conversion_factors[i][t]
                            rhs = block.INPUT_GROUP_FLOW[n, g, p, t] * flow_share[t]
                            block.input_flow_share_relation.add(
                                (n, i, flow_share_type, p, t),
                                op(lhs, rhs),
                            )

        self.input_flow_share_relation_build = BuildAction(
            rule=_input_flow_share_relation
        )

        self.output_flow_share_relation = Constraint(
            [
                (n, o, c, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for o in n.outputs
                for c in CONSTRAINT_TYPES
            ],
            noruleinit=True,
        )

        def _output_flow_share_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    for (
                        flow_share_type,
                        shares,
                    ) in n.output_flow_shares.items():
                        op = _get_operator_from_constraint_type(flow_share_type)
                        for o, flow_share in shares.items():
                            # Find related output group for given input node:
                            g = next(
                                g
                                for g, outputs in n.output_groups.items()
                                if o in outputs
                            )
                            lhs = m.flow[n, o, p, t] / n.conversion_factors[o][t]
                            rhs = block.OUTPUT_GROUP_FLOW[n, g, p, t] * flow_share[t]
                            block.output_flow_share_relation.add(
                                (n, o, flow_share_type, p, t), op(lhs, rhs)
                            )

        self.output_flow_share_relation_build = BuildAction(
            rule=_output_flow_share_relation
        )

        self.emission_relation = Constraint(
            [
                (n, o, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for o in n.emission_factors
            ],
            noruleinit=True,
        )

        def _emission_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    for o, emissions in n.emission_factors.items():
                        rhs = m.flow[n, o, p, t]
                        lhs = 0
                        for e, emission_factor in emissions.items():
                            if e in n.input_groups:
                                emitting_node = block.INPUT_GROUP_FLOW[n, e, p, t]
                            elif e in n.output_groups:
                                emitting_node = block.OUTPUT_GROUP_FLOW[n, e, p, t]
                            elif e in n.inputs:
                                emitting_node = m.flow[e, n, p, t]
                            elif e in n.outputs:
                                emitting_node = m.flow[n, e, p, t]
                            else:
                                KeyError(
                                    f"Emitting node '{e}' not found in inputs or outputs (including groups)."
                                )
                            lhs += emitting_node * emission_factor[t]
                        block.emission_relation.add((n, o, p, t), lhs == rhs)

        self.emission_relation_build = BuildAction(rule=_emission_relation)

        self.output_activity_bound_relation = Constraint(
            [
                (n, c, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for c in CONSTRAINT_TYPES
            ],
            noruleinit=True,
        )

        def _output_activity_bound_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    for constraint_type, activity_bound in n.activity_bounds.items():
                        op = _get_operator_from_constraint_type(constraint_type)
                        g = list(n.output_groups)[0]
                        lhs = block.OUTPUT_GROUP_FLOW[n, g, p, t]
                        rhs = activity_bound[t]
                        block.output_activity_bound_relation.add(
                            (n, constraint_type, p, t),
                            op(lhs, rhs),
                        )

        self.output_activity_bound_relation_build = BuildAction(
            rule=_output_activity_bound_relation
        )


@dataclasses.dataclass(unsafe_hash=False, frozen=False, eq=False)
class MIMO(MultiInputMultiOutputConverter, Facade):
    """Facade for MultiInputMultiOutputConverter component.

    This class provides a facade to use MultiInputMultiOutputConverter with
    oemof.tabular.
    Pre-inits mimo specific parameters and drops them from `kwargs`: busses,
    conversion_factors, emission_factors, flow_shares and activity_bounds.
    Then, initializes MultiInputMultiOutputConverter.

    If component is expandable the investment is set on the primary bus which
    has to be defined by the keyword 'primary'.

    You can add 'groups' to group certain inputs or output, e.g.
    {"in": ["IISGAS-LB", "IISHH2-LB"], "out": ["IISELC-LB", "IISHTH-LB"]}.

    Naming conventions:
    - input buses start with 'from_bus'
    - output busses start with 'to_bus'
    - conversion factors: 'conversion_factor_<group_or_bus_name>'
    - emission factors are defined by the group or bus label the emission is
      associated with and the emission bus label itself:
        'emission_factor_<group_or_bus_name>_<emission_bus_name>', e.g.
        emission_factor_out_INDCH4N: ch4 emission associated with 'out' group
    - flow shares: 'flow_share_<fix/min/max>_<bus_name>'
    - activity bounds: 'activity_bound_<fix/max/min>

    """

    carrier: str
    tech: str

    def __init__(self, **kwargs):
        if "primary" in kwargs and not isinstance(kwargs["primary"], str):
            raise TypeError(
                "Primary key must be given as string, not as Bus component. "
                "Eventually, you must remove field 'primary' from foreign keys in datapackage.json."
            )
        buses = {
            key: value
            for key, value in kwargs.items()
            if hasattr(value, "type") and value.type == "bus"
        }
        groups = kwargs.get("groups", {})

        # Init investment
        self.capacity_cost: float = kwargs.get("capacity_cost")
        self.expandable: bool = kwargs.get("expandable", False)
        self.capacity_potential: float = kwargs.get("capacity_potential", float("+inf"))
        self.capacity_minimum: float = kwargs.get("capacity_minimum")

        inputs, outputs = self._init_inputs_and_outputs(buses, kwargs)
        conversion_factors = self._init_efficiencies(buses, groups, kwargs)
        emission_factors = self._init_emissions(buses, groups, kwargs)
        flow_shares = self._init_facade_flow_shares(buses, kwargs)
        activity_bounds = self._init_facade_activity_bounds(kwargs)

        super().__init__(
            inputs=inputs,
            outputs=outputs,
            conversion_factors=conversion_factors,
            emission_factors=emission_factors,
            flow_shares=flow_shares,
            activity_bounds=activity_bounds,
            **kwargs,
        )

    def _init_inputs_and_outputs(self, buses, kwargs):
        def create_flow(bus):
            """If component is expandable, put investment on primary bus."""
            investment = self._investment()
            if not investment:
                return Flow()
            if investment and "primary" not in kwargs:
                raise AttributeError(
                    "If you want to set investment you have to define primary bus to put investment on."
                )
            if bus.label == kwargs["primary"]:
                return Flow(nominal_value=investment)
            return Flow()

        inputs = {}
        outputs = {}

        if "groups" in kwargs:
            for group_name, bus_names in kwargs["groups"].items():
                # get bus direction: input or output (from/to
                group_direction = None
                for from_to_name, bus in buses.items():
                    if bus.label not in bus_names:
                        continue
                    # Remove grouped bus from kwargs so that it is not added twice
                    kwargs.pop(from_to_name)
                    # Detect whether group is input or output group
                    if group_direction is None:
                        group_direction = from_to_name.split("_")[0]
                    if group_direction != from_to_name.split("_")[0]:
                        raise RuntimeError(
                            f"Mix of input and output buses in group '{group_name}'."
                        )
                # add multiple input/output to `inputs` or `outputs`
                group_dict = {
                    bus: create_flow(bus)
                    for bus in buses.values()
                    if bus.label in bus_names
                }
                if len(group_dict) != len(bus_names):
                    raise LookupError(
                        f"Could not find all buses form group '{group_name}'."
                    )
                if group_direction == "from":
                    inputs[group_name] = group_dict
                if group_direction == "to":
                    outputs[group_name] = group_dict
            kwargs.pop("groups")

        for key, bus in list(kwargs.items()):
            if key.startswith("from_bus"):
                inputs[bus] = create_flow(bus)
                kwargs.pop(key)
            if key.startswith("to_bus"):
                outputs[bus] = create_flow(bus)
                kwargs.pop(key)

        return inputs, outputs

    @staticmethod
    def _init_efficiencies(buses, groups, kwargs):
        conversion_factors = {}
        for key, value in list(kwargs.items()):
            if key.startswith("conversion_factor"):
                # get bus or group name
                bus_label = key[len("conversion_factor_") :]
                # search bus, if bus does not exist: bus_label is a group name
                bus = [bus for bus in buses.values() if bus.label == bus_label]
                if bus:
                    conversion_factors[bus[0]] = value
                else:
                    # it's a group
                    if bus_label not in groups:
                        raise LookupError(
                            f"Could not find bus '{bus_label}' for efficiency labeled '{key}'."
                        )
                    conversion_factors[bus_label] = value
                kwargs.pop(key)

        return conversion_factors

    @staticmethod
    def _init_emissions(buses, groups, kwargs):
        emission_factors = {}
        for key, value in list(kwargs.items()):
            if key.startswith("emission_factor"):
                # search from_bus in `buses` and `groups` and write from_bus / to_bus options in dict
                suffixes = key.split("_")[2:]
                bus_options = {}
                for i in range(len(suffixes)):
                    part = "_".join(suffixes[: i + 1])
                    bus = [bus for bus in buses.items() if bus[1].label == part]
                    group = [group for group in groups if group == part]
                    if bus:
                        to_bus_name = "_".join(suffixes[i + 1 :])
                        bus_options.update({bus[0][1]: to_bus_name})
                    if group:
                        to_bus_name = "_".join(suffixes[i + 1 :])
                        bus_options.update({group[0]: to_bus_name})
                # search to_bus in `buses` and `groups` for all combinations and write to new dict
                bus_combinations = {}  # todo tuples instead?
                for from_bus, to_bus_name in list(bus_options.items()):
                    bus = [bus for bus in buses.items() if bus[1].label == to_bus_name]
                    group = [group for group in groups if group == to_bus_name]
                    if bus:
                        bus_combinations.update({from_bus: bus[0][1]})
                    if group:
                        bus_combinations.update({from_bus: group[0]})
                # add emission factors and raise error if there is more than one combination of bus/group names found
                if len(bus_combinations) == 1:
                    from_bus = list(bus_combinations.keys())[0]
                    to_bus = list(bus_combinations.values())[0]
                    try:
                        # entry already exists and is updated
                        emission_factors[to_bus].update({from_bus: value})
                    except KeyError:
                        # add new entry for `to_bus`
                        emission_factors[to_bus] = {from_bus: value}
                    kwargs.pop(key)
                elif len(bus_combinations) == 0:
                    pass  # todo raise error
                elif len(bus_combinations) > 1:
                    pass  # todo raise error

        return emission_factors

    @staticmethod
    def _init_facade_flow_shares(buses, kwargs):
        flow_shares = {}
        for key, value in list(kwargs.items()):
            if key.startswith("flow_share"):
                share_type = key.split("_")[2]
                bus_label = "_".join(key.split("_")[3:])
                bus = [bus for bus in buses.items() if bus[1].label == bus_label]
                if bus:
                    bus_entry = bus[0][1]
                else:
                    # it's a group
                    bus_entry = bus_label
                try:
                    # entry already exists and is updated
                    flow_shares[share_type].update({bus_entry: value})
                except KeyError:
                    # add new entry for `to_bus`
                    flow_shares[share_type] = {bus_entry: value}
                kwargs.pop(key)
        return flow_shares

    @staticmethod
    def _init_facade_activity_bounds(kwargs):
        activity_bounds = {}
        for key, value in list(kwargs.items()):
            if key.startswith("activity_bound"):
                constraint_type = key.split("_")[2]
                activity_bounds[constraint_type] = value
                kwargs.pop(key)
        return activity_bounds
