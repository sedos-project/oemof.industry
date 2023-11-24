# -*- coding: utf-8 -*-
"""
Example that illustrates how to use component `MultiInputMultiOutputConverter`.

SPDX-License-Identifier: MIT
"""
import pandas as pd
import pytest

from oemof.solph import EnergySystem
from oemof.solph import Model
from oemof.solph import processing
from oemof.solph.buses import Bus
from oemof.solph.components import Sink
from oemof.solph.components import Source
from oemof.solph.flows import Flow

from mimo_converter import MultiInputMultiOutputConverter


def test_invalid_flow_shares():
    with pytest.raises(ValueError, match="Invalid flow share types found: {'maxx'}"):
        b_gas = Bus(label="gas")
        b_hydro = Bus(label="hydro")
        b_electricity = Bus(label="electricity")
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={b_electricity: Flow()},
            input_flow_shares={"maxx": {b_gas: 0.4}},
        )

    with pytest.raises(
        ValueError,
        match="Cannot combine 'fix' and 'min' flow share for same node.",
    ):
        b_gas = Bus(label="gas")
        b_hydro = Bus(label="hydro")
        b_electricity = Bus(label="electricity")
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={b_electricity: Flow()},
            input_flow_shares={"min": {b_gas: 0.4}, "fix": {b_gas: 0.4}},
        )

    with pytest.raises(
        ValueError,
        match="Cannot combine 'fix' and 'max' flow share for same node.",
    ):
        b_gas = Bus(label="gas")
        b_hydro = Bus(label="hydro")
        b_electricity = Bus(label="electricity")
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={b_electricity: Flow()},
            input_flow_shares={"max": {b_gas: 0.4}, "fix": {b_gas: 0.4}},
        )


def test_multiple_inputs():
    idx = pd.date_range("1/1/2017", periods=2, freq="H")
    es = EnergySystem(timeindex=idx)

    # resources
    b_gas = Bus(label="gas")
    es.add(b_gas)
    es.add(
        Source(
            label="gas_station",
            outputs={b_gas: Flow(fix=[120, 0], nominal_value=1, variable_costs=20)},
        )
    )

    b_hydro = Bus(label="hydro")
    es.add(b_hydro)
    es.add(
        Source(
            label="hydro_station",
            outputs={b_hydro: Flow(fix=[0, 130], nominal_value=1, variable_costs=20)},
        )
    )

    b_electricity = Bus(label="electricity")
    es.add(b_electricity)
    es.add(
        Sink(
            label="demand",
            inputs={b_electricity: Flow(fix=[100, 100], nominal_value=1)},
        )
    )

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={b_electricity: Flow()},
            conversion_factors={b_gas: 1.2, b_hydro: 1.3},
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    assert all(
        results[("gas", "mimo")]["sequences"]["flow"].values[:-1] == [120.0, 0.0]
    )
    assert all(
        results[("hydro", "mimo")]["sequences"]["flow"].values[:-1] == [0.0, 130.0]
    )


def test_flow_shares():
    idx = pd.date_range("1/1/2017", periods=2, freq="H")
    es = EnergySystem(timeindex=idx)

    # resources
    b_gas = Bus(label="gas")
    es.add(b_gas)
    es.add(Source(label="gas_station", outputs={b_gas: Flow(variable_costs=20)}))

    b_hydro = Bus(label="hydro")
    es.add(b_hydro)
    es.add(Source(label="hydro_station", outputs={b_hydro: Flow(variable_costs=20)}))

    b_electricity = Bus(label="electricity")
    es.add(b_electricity)
    es.add(
        Sink(
            label="demand",
            inputs={b_electricity: Flow(fix=[100, 100], nominal_value=1)},
        )
    )

    b_heat = Bus(label="heat", balanced=False)
    es.add(b_heat)

    b_heat_low = Bus(label="heat_low", balanced=False)
    es.add(b_heat)

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={
                b_electricity: Flow(),
                "heat": {b_heat: Flow(), b_heat_low: Flow()},
            },
            conversion_factors={b_gas: 1.2, b_hydro: 1.3},
            input_flow_shares={"fix": {b_gas: [0.8, 0.3]}},
            output_flow_shares={"fix": {b_heat: 0.8}},
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    assert results[("gas", "mimo")]["sequences"]["flow"].values[0] == 100 * 0.8 * 1.2
    assert results[("gas", "mimo")]["sequences"]["flow"].values[1] == 100 * 0.3 * 1.2
    assert results[("hydro", "mimo")]["sequences"]["flow"].values[0] == 100 * 0.2 * 1.3
    assert results[("hydro", "mimo")]["sequences"]["flow"].values[1] == 100 * 0.7 * 1.3
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[0] == 100
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[1] == 100
    assert results[("mimo", "heat")]["sequences"]["flow"].values[0] == 80
    assert results[("mimo", "heat")]["sequences"]["flow"].values[1] == 80
    assert results[("mimo", "heat_low")]["sequences"]["flow"].values[0] == 20
    assert results[("mimo", "heat_low")]["sequences"]["flow"].values[1] == 20


def test_emissions():
    idx = pd.date_range("1/1/2017", periods=2, freq="H")
    es = EnergySystem(timeindex=idx)

    # Buses
    b_gas = Bus(label="gas")
    es.add(b_gas)
    es.add(Source(label="gas_station", outputs={b_gas: Flow(variable_costs=20)}))

    b_hydro = Bus(label="hydro")
    es.add(b_hydro)
    es.add(Source(label="hydro_station", outputs={b_hydro: Flow(variable_costs=20)}))

    b_electricity = Bus(label="electricity")
    es.add(b_electricity)
    es.add(
        Sink(
            label="demand",
            inputs={b_electricity: Flow(fix=[100, 100], nominal_value=1)},
        )
    )

    b_heat = Bus(label="heat", balanced=False)
    es.add(b_heat)

    b_heat_low = Bus(label="heat_low", balanced=False)
    es.add(b_heat)

    b_co2 = Bus(label="co2", balanced=False)
    es.add(b_co2)

    b_ch4 = Bus(label="ch4", balanced=False)
    es.add(b_ch4)

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={
                b_electricity: Flow(),
                "heat": {
                    b_heat: Flow(),
                    b_heat_low: Flow(),
                },
                b_co2: Flow(),
                b_ch4: Flow(),
            },
            emission_factors={
                b_co2: {b_gas: 0.8, b_hydro: 0.6},
                b_ch4: {b_gas: 0.4, b_hydro: 0.2},
            },
            conversion_factors={b_gas: 1.2, b_hydro: 1.3},
            input_flow_shares={"fix": {b_gas: [0.8, 0.3]}},
            output_flow_shares={"fix": {b_heat_low: 0.2}},
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    assert results[("gas", "mimo")]["sequences"]["flow"].values[0] == 100 * 0.8 * 1.2
    assert results[("gas", "mimo")]["sequences"]["flow"].values[1] == 100 * 0.3 * 1.2
    assert results[("hydro", "mimo")]["sequences"]["flow"].values[0] == 100 * 0.2 * 1.3
    assert results[("hydro", "mimo")]["sequences"]["flow"].values[1] == 100 * 0.7 * 1.3
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[0] == 100
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[1] == 100
    assert results[("mimo", "heat")]["sequences"]["flow"].values[0] == 80
    assert results[("mimo", "heat")]["sequences"]["flow"].values[1] == 80
    assert results[("mimo", "heat_low")]["sequences"]["flow"].values[0] == 20
    assert results[("mimo", "heat_low")]["sequences"]["flow"].values[1] == 20

    # Emissions
    assert results[("mimo", "co2")]["sequences"]["flow"].values[0] == pytest.approx(
        results[("gas", "mimo")]["sequences"]["flow"].values[0] * 0.8
        + results[("hydro", "mimo")]["sequences"]["flow"].values[0] * 0.6
    )
    assert results[("mimo", "co2")]["sequences"]["flow"].values[1] == pytest.approx(
        results[("gas", "mimo")]["sequences"]["flow"].values[1] * 0.8
        + results[("hydro", "mimo")]["sequences"]["flow"].values[1] * 0.6
    )
    assert results[("mimo", "ch4")]["sequences"]["flow"].values[0] == pytest.approx(
        results[("gas", "mimo")]["sequences"]["flow"].values[0] * 0.4
        + results[("hydro", "mimo")]["sequences"]["flow"].values[0] * 0.2
    )
    assert results[("mimo", "ch4")]["sequences"]["flow"].values[1] == pytest.approx(
        results[("gas", "mimo")]["sequences"]["flow"].values[1] * 0.4
        + results[("hydro", "mimo")]["sequences"]["flow"].values[1] * 0.2
    )
