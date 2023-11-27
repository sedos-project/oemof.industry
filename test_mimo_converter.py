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
    es.add(b_heat_low)

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


def test_industry_component_INDIFTHTHGAS00():
    idx = pd.date_range("1/1/2017", periods=6, freq="H")
    es = EnergySystem(timeindex=idx)

    # Buses
    b_gas = Bus(label="INDGAS_OTH")
    es.add(b_gas)
    es.add(Source(label="gas_station", outputs={b_gas: Flow()}))

    b_hydro = Bus(label="INDHH2_OTH")
    es.add(b_hydro)
    es.add(Source(label="hydro_station", outputs={b_hydro: Flow()}))

    b_heat = Bus(label="IFTHTH")
    es.add(b_heat)
    es.add(
        Sink(
            label="heat_demand",
            inputs={b_heat: Flow(fix=[66.2256, 66.2256,	66.2256, 0,	0, 16.5564], nominal_value=1)},
        )
    )

    b_ch4 = Bus(label="INDCH4N", balanced=False)
    es.add(b_ch4)

    b_co2 = Bus(label="INDCO2N", balanced=False)
    es.add(b_co2)

    b_n2o = Bus(label="INDN2ON", balanced=False)
    es.add(b_n2o)

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={
                b_heat: Flow(),
                b_co2: Flow(),
                b_ch4: Flow(),
                b_n2o: Flow(),
            },
            emission_factors={
                b_co2: {b_gas: 56},
                b_ch4: {b_gas: 0.0012},
                b_n2o: {b_gas: 0.0006},
            },
            conversion_factors={b_heat: 0.82},
            input_flow_shares={"max": {b_hydro: [0, 0, 0, 0.5, 1, 1]}},
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    # INPUTS
    # Gas
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[0] == pytest.approx(80.7629)
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[1] == pytest.approx(80.7629)
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[2] == pytest.approx(80.7629)
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("INDGAS_OTH", "mimo")]["sequences"]["flow"].values[5] == pytest.approx(0)
    # Hydro
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[0] == pytest.approx(0)
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[1] == pytest.approx(0)
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[2] == pytest.approx(0)
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("INDHH2_OTH", "mimo")]["sequences"]["flow"].values[5] == pytest.approx(20.1907, rel=1e-3)

    # OUTPUTS
    # Heat (Primary)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[0] == pytest.approx(66.2256)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[1] == pytest.approx(66.2256)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[2] == pytest.approx(66.2256)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("mimo", "IFTHTH")]["sequences"]["flow"].values[5] == pytest.approx(16.5564)
    # CH4
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[0] == pytest.approx(0.0969, rel=1e-3)
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[1] == pytest.approx(0.0969, rel=1e-3)
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[2] == pytest.approx(0.0969, rel=1e-3)
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("mimo", "INDCH4N")]["sequences"]["flow"].values[5] == pytest.approx(0)
    # CO2
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[0] == pytest.approx(4522.72)
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[1] == pytest.approx(4522.72)
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[2] == pytest.approx(4522.72)
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("mimo", "INDCO2N")]["sequences"]["flow"].values[5] == pytest.approx(0)
    # N2O
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[0] == pytest.approx(0.0485, rel=1e-3)
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[1] == pytest.approx(0.0485, rel=1e-3)
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[2] == pytest.approx(0.0485, rel=1e-3)
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[3] == pytest.approx(0)
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[4] == pytest.approx(0)
    assert results[("mimo", "INDN2ON")]["sequences"]["flow"].values[5] == pytest.approx(0)
