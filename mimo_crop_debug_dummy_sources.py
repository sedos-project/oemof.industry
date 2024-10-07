import dash_core_components
import pandas as pd
import numpy as np
from oemof import solph
from oemof.solph import EnergySystem, Investment, Model, processing
from oemof.solph.buses import Bus
from oemof.solph.components import Sink, Source
from oemof.solph.flows import Flow
from oemof.solph.constraints import equate_variables

from oemof_industry.mimo_converter import MultiInputMultiOutputConverter
import plotly.graph_objects as go
from dash import html, dcc, Dash


if __name__=="__main__":

    df = pd.read_csv("crop_static.csv", index_col=0, parse_dates=True)
    #df = df.iloc[10:20]
    idx = df.index #pd.date_range("1/1/2017", periods=2, freq="H")
    idx.freq = "h"
    es = EnergySystem(timeindex=idx, infer_last_interval=False)
    prof_1 = df["ghi"].values
    prof_2 = df["tp"].values
    prof_3 = df["irrigation"].values

    # resources
    b_in1 = Bus(label="sun_bus")  #volatile
    es.add(b_in1)
    es.add(
        Source(
            label="sun",
            outputs={
                b_in1: Flow(),
            },
        )
    )

    b_in2 = Bus(label="rain_bus")  #volatile
    es.add(b_in2)
    es.add(
        Source(
            label="rain",
            outputs={
                b_in2: Flow(),
            },
        )
    )

    b_in3 = Bus(label="irrigation_bus")  #Volatile
    es.add(b_in3)
    es.add(
        Source(
            label="irrigation",
            outputs={
                b_in3: Flow()
            },
        )
    )

    b_crop = Bus(label="b_crop")
    es.add(b_crop)
    es.add(
        Sink(
            label="crop",
            inputs={b_crop: Flow(variable_costs=-2e-3)}, # this value is a bit arbitrary, with -1e-6 it did not work
        )
    )
    es.add(
        Sink(
            label="excess_crop",
            inputs={b_crop: Flow(variable_costs=1e-6)},
        )
    )

    b_biomass = Bus(label="b_biomass")
    es.add(b_biomass)
    es.add(
        Sink(
            label="biomass",
            inputs={b_biomass: Flow()},
        )
    )
    es.add(
        Sink(
            label="excess_biomass",
            inputs={b_biomass: Flow(variable_costs=1e-6)},
        )
    )


    ci1 = prof_1
    ci2 = prof_2
    ci3 = prof_3

    co1 = df["total_biomass"].values * 0.68 #in the model this depends on input profiles
    co2 = df["total_biomass"].values * (1-0.68)# df["remaining_biomass"].values # in the model this is 1-co1

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={
                b_in1: Flow(),
                b_in2: Flow(),
                b_in3: Flow()
            },
            outputs={
                b_crop: Flow(fix=df["total_biomass"].values * 0.68, nominal_value=100),
                b_biomass: Flow(),

            },
            #flow_shares={"fix": {b_crop: 0.68}},
            conversion_factors={
                b_in1: ci1,
                b_in2: ci2,
                b_in3: ci3,
                b_crop: co1,
                b_biomass: co2,
            },
        )
    )

    from oemof_visio import ESGraphRenderer

    gr = ESGraphRenderer(energy_system=es, filepath="mimo_example")
    gr.render()

    # create an optimization problem and solve it
    om = Model(es)

    # equate_variables(
    #     om,
    #     om.InvestmentFlowBlock.invest[es.groups["sun"], b_in1, 0],
    #     om.InvestmentFlowBlock.invest[es.groups["mimo"], b_el, 0],
    # )
    import time
    t0=time.time()
    # solve model
    om.solve(solver="cbc")
    print(f"took {time.time()-t0}")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    # print(f"invest mimo1 {results[('sun_bus', 'mimo')]['scalars'].invest}")
    # print(f"invest mimo2 {results[('mimo', 'b_el')]['scalars'].invest}")
    # print(results[("in1", "b_in1")]["scalars"])
    # cap_i1 = results[("sun", "sun_bus")]["scalars"].invest
    # cap_i2 = results[("rain", "rain_bus")]["scalars"].invest
    # print(f"invest in1: {cap_i1}, invest in2: {cap_i2}")
    fi1 = results[("sun_bus", "mimo")]["sequences"]["flow"].values
    fi2 = results[("rain_bus", "mimo")]["sequences"]["flow"].values
    fi3 = results[("irrigation_bus", "mimo")]["sequences"]["flow"].values

    # print("inputs")
    #
    # for p1,p2, v1, v2, v3 in zip(prof_1, prof_2, fi1, fi2, fi3):
    #     print(p1,p2)
    #     print(v1, v2, v3)
        # print(v1 / (v1 + v2 + v3))
        # print(v2 / (v1 + v2 + v3))
        # print(v3 / (v1 + v2 + v3))
        #assert p*cap_i1 >= v1

    fo1 = results[("mimo", "b_crop")]["sequences"]["flow"].values
    fo2 = results[("mimo", "b_biomass")]["sequences"]["flow"].values

    print(f"Total Sun: {np.nansum(fi1)*1e-6}M")
    print(f"Total Irrigation: {np.nansum(fi3)*1e-3}k")
    print(f"Total Rain: {np.nansum(fi2)*1e-3}k")
    print(f"Total Crop: {np.nansum(fo1)}")
    print(f"Total Biomass: {np.nansum(fo2)}")

    fig_dict = gr.sankey(results)
    # print("outputs")
    # for v1, v2, v3 in zip(fo1, fo2, fo3):
    #     print(v1,v2,v3)

        # print(v1 / (v1 + v2 +v3))
        # print(v2 / (v1 + v2 +v3))
        # print(v3 / (v1 + v2 +v3))

    bus_figures = []


    for nd in es.nodes:
        if isinstance(nd, Bus):
            bus = nd.label
            fig = go.Figure(layout=dict(title=f"{bus} bus node"))
            for t, g in solph.views.node(results, node=bus)["sequences"].items():
                idx_asset = abs(t[0].index(bus) - 1)

                fig.add_trace(
                    go.Scatter(
                        x=g.index, y=g.values * pow(-1, idx_asset), name=t[0][idx_asset]
                    )
                )

        bus_figures.append(fig)


    fig = go.Figure(data=fig_dict)

    app = Dash(__name__)
    app.title = "CROP-dummy sources"
    app.layout = html.Div(
        [dcc.Graph(figure=fig)] + [
            dcc.Graph(
                figure=fig,
            )
            for fig in bus_figures
        ]
    )

    app.run_server(debug=False, port=8070)

    import pdb;pdb.set_trace()

    # assert results[("b_in", "mimo")]["sequences"]["flow"].values[0] == 100 * 0.8 * 1.2
    # assert results[("b_in", "mimo")]["sequences"]["flow"].values[1] == 100 * 0.3 * 1.2
    # assert results[("mimo", "b_out1")]["sequences"]["flow"].values[0] == 100
    # assert results[("mimo", "b_out1")]["sequences"]["flow"].values[1] == 100
    # assert results[("mimo", "b_biomass1")]["sequences"]["flow"].values[0] == 80
    # assert results[("mimo", "b_biomass1")]["sequences"]["flow"].values[1] == 80
    # assert results[("mimo", "b_biomass2")]["sequences"]["flow"].values[0] == 20
    # assert results[("mimo", "b_biomass2")]["sequences"]["flow"].values[1] == 20