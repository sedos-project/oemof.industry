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
from oemof.tabular._facade import Facade, dataclass_facade
from pyomo.core import BuildAction, Constraint
from pyomo.core.base.block import ScalarBlock
from pyomo.environ import NonNegativeReals, Set, Var

FLOW_SHARE_TYPES = ("min", "max", "fix")


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
    emissions : dict
        Dictionary with emission outflows, holding a dict with contributing
        input nodes and related conversion factors.
    conversion_factors : dict
        Dictionary containing conversion factors for conversion of each flow.
        Keys must be the connected nodes (typically Buses).
        The dictionary values can either be a scalar or an iterable with
        individual conversion factors for each time step.
        Default: 1. If no conversion_factor is given for an in- or outflow, the
        conversion_factor is set to 1.
    input_flow_shares : dict
        Dictionary containing flow shares which shall be hold within related
        input group. Keys must be connected input nodes (typically Buses).
        The dictionary values can either be a scalar or an iterable with
        individual flow shares for each time step. If no flow share is given
        for an input flow, no share is set for this flow.
    output_flow_shares : dict
        Dictionary containing flow shares which shall be hold within related
        input group. Keys must be connected input nodes (typically Buses).
        The dictionary values can either be a scalar or an iterable with
        individual flow shares for each time step. If no flow share is given
        for an input flow, no share is set for this flow.

    # todo: update parameter list

    Examples
    --------
    Defining a MIMO-converter:

    >>> from oemof import solph
    >>> bgas = solph.buses.Bus(label='natural_gas')
    >>> bcoal = solph.buses.Bus(label='hard_coal')
    >>> bel = solph.buses.Bus(label='electricity')
    >>> bheat = solph.buses.Bus(label='heat')

    >>> trsf = solph.components.Converter(
    ...    label='pp_gas_1',
    ...    inputs={bgas: solph.flows.Flow(), bcoal: solph.flows.Flow()},
    ...    outputs={bel: solph.flows.Flow(), bheat: solph.flows.Flow()},
    ...    conversion_factors={bel: 0.3, bheat: 0.5,
    ...                        bgas: 0.8, bcoal: 0.2})
    >>> print(sorted([x[1][5] for x in trsf.conversion_factors.items()]))
    [0.2, 0.3, 0.5, 0.8]

    >>> type(trsf)
    <class 'oemof.solph.components._converter.Converter'>

    >>> sorted([str(i) for i in trsf.inputs])
    ['hard_coal', 'natural_gas']

    >>> trsf_new = solph.components.Converter(
    ...    label='pp_gas_2',
    ...    inputs={bgas: solph.flows.Flow()},
    ...    outputs={bel: solph.flows.Flow(), bheat: solph.flows.Flow()},
    ...    conversion_factors={bel: 0.3, bheat: 0.5})
    >>> trsf_new.conversion_factors[bgas][3]
    1

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

        self.input_groups = self._unify_groups(inputs)
        self.output_groups = self._unify_groups(outputs, exclude=emissions)

        inputs = reduce(operator.ior, self.input_groups.values(), {})
        # Add emissions to outputs (as they are excluded from output groups before)
        outputs = reduce(operator.ior, self.output_groups.values(), {}) | emissions

        if custom_attributes is None:
            custom_attributes = {}

        super().__init__(
            label=label,
            inputs=inputs,
            outputs=outputs,
            **custom_attributes,
        )

        self.conversion_factors = self._init_conversion_factors(conversion_factors)

        self._check_flow_shares(flow_shares)
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
    def _check_flow_shares(flow_shares):
        if flow_shares is None:
            return

        # Check for invalid share types
        invalid_flow_share_types = set(flow_shares) - set(FLOW_SHARE_TYPES)
        if invalid_flow_share_types:
            raise ValueError(
                f"Invalid flow share types found: {invalid_flow_share_types}. "
                "Must be one of 'min', 'max' or 'fix'."
            )

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
                new_group = f"group_{group_counter}"
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
    :class:`~oemof.solph.components._converter.ConverterBlock`

    **The following sets are created:** (-> see basic sets at
    :class:`.Model` )

    CONVERTERS
        A set with all
        :class:`~oemof.solph.components._converter.Converter` objects.

    **The following constraints are created:**

    Linear relation :attr:`om.ConverterBlock.relation[i,o,t]`
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
        """Creates the linear constraint for the class:`ConverterBlock`
        block.

        Parameters
        ----------

        group : list
            List of oemof.solph.components.Converters objects for which
            the linear relation of inputs and outputs is created
            e.g. group = [trsf1, trsf2, trsf3, ...]. Note that the relation
            is created for all existing relations of all inputs and all outputs
            of the converter. The components inside the list need to hold
            an attribute `conversion_factors` of type dict containing the
            conversion factors for all inputs to outputs.
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

        self.input_output_group_relation = Constraint(  # todo: WARNING Element (MIMO(carrier='exo_steel', tech='mimo'), 'group_0', 0, 8754) already exists in Set OrderedScalarSet; no action taken
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

        def _get_operator_from_flow_share_type(flow_share_type):
            if flow_share_type == "min":
                return operator.ge
            if flow_share_type == "max":
                return operator.le
            if flow_share_type == "fix":
                return operator.eq
            raise ValueError(f"Unknown flow share type: {flow_share_type}")

        self.input_flow_share_relation = Constraint(
            [
                (n, i, s, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for i in n.inputs
                for s in FLOW_SHARE_TYPES
            ],
            noruleinit=True,
        )

        def _input_flow_share_relation(block):
            for p, t in m.TIMEINDEX:
                for n in group:
                    for flow_share_type, shares in n.input_flow_shares.items():
                        op = _get_operator_from_flow_share_type(flow_share_type)
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
                (n, o, s, p, t)
                for p, t in m.TIMEINDEX
                for n in group
                for o in n.outputs
                for s in FLOW_SHARE_TYPES
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
                        op = _get_operator_from_flow_share_type(flow_share_type)
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


class MIMO(MultiInputMultiOutputConverter, Facade):
    """Facade for MIMO component.

    Pre-inits mimo specific parameters and drops them from `kwargs`: busses,
    conversion_factors, emission_factors, and flow_shares.

    # todo naming convention for parameters (keys in csv) is required. Keys of busses start with "from_bus" or "to_bus", respectively. groups, etc.

    Parameters
    ----------
    carrier :

    tech :


    """

    carrier: str
    tech: str

    def __init__(self, **kwargs):
        inputs = {}
        outputs = {}
        conversion_factors = {}
        emission_factors = {}
        flow_shares = {}
        groups = {}

        # get all busses for later processing
        buses = {
            key: value
            for key, value in kwargs.items()
            if hasattr(value, "type") and value.type == "bus"
        }

        # add multiple inputs/outputs according to groups
        if "groups" in kwargs:
            groups = kwargs["groups"]
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
                group_dict = {bus: Flow() for bus in buses.values() if bus.label in bus_names}
                if len(group_dict) != len(bus_names):
                    raise LookupError(f"Could not find all buses form group '{group_name}'.")
                if group_direction == "from":
                    inputs[group_name] = group_dict
                if group_direction == "to":
                    outputs[group_name] = group_dict
            kwargs.pop("groups")

        # add remaining, single inputs and outputs, and other parameters
        for key, value in list(kwargs.items()):
            if key.startswith("from_bus"):
                inputs[value] = Flow()
                kwargs.pop(key)
            elif key.startswith("to_bus"):
                outputs[value] = Flow()
                kwargs.pop(key)
            elif key.startswith("efficiency"):
                # get bus or group name
                bus_label = "_".join(key.split("_")[1:])
                # search bus, if bus does not exist: bus_label is a group name
                bus = [bus for bus in buses.values() if bus.label == bus_label]
                if bus:
                    conversion_factors[bus[0]] = value
                else:
                    # it's a group
                    if bus_label not in groups:
                        raise LookupError(f"Could not find bus '{bus_label}' for efficiency labeled '{key}'.")
                    conversion_factors[bus_label] = value
                kwargs.pop(key)
            elif key.startswith("emission_factor"):
                # search from_bus in `busses` and `groups` and write from_bus / to_bus options in dict
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
                # search to_bus in `busses` and `groups` for all combinations and write to new dict
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
            elif key.startswith("flow_share"):
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

        super().__init__(
            inputs=inputs,
            outputs=outputs,
            conversion_factors=conversion_factors,
            emission_factors=emission_factors,
            flow_shares=flow_shares,
            **kwargs,
        )
