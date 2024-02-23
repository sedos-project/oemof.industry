import pathlib

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa
from oemof.tabular.facades import Bus, Commodity, Conversion, Excess, Load

from oemof_industry.mimo_converter import MIMO
from tests.test_mimo_converter import check_results_for_IIS_CHPSTMGAS101_LB


def test_datapackage_results_for_IIS_CHPSTMGAS101_LB():
    MIMO_DATAPACKAGE = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "IIS_CHPSTMGAS101_LB"
        / "datapackage.json"
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
    m.solve("cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(m))
    check_results_for_IIS_CHPSTMGAS101_LB(results)
