import pathlib

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa
from oemof.tabular.facades import Bus, Commodity, Conversion, Excess, Load

from oemof_industry.mimo_converter import MIMO
from tests.test_mimo_converter import check_results_for_IIS_CHPSTMGAS101_LB
from tests.test_mimo_investment import check_results_for_investment_var_output


TYPEMAP = {
    "bus": Bus,
    "commodity": Commodity,
    "conversion": Conversion,
    "excess": Excess,
    "load": Load,
    "mimo": MIMO,
}


def test_datapackage_results_for_IIS_CHPSTMGAS101_LB():
    datapackage_path = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "IIS_CHPSTMGAS101_LB"
        / "datapackage.json"
    )
    es = EnergySystem.from_datapackage(
        str(datapackage_path), attributemap={}, typemap=TYPEMAP
    )

    m = Model(es)
    m.solve("cbc")

    results = processing.convert_keys_to_strings(processing.results(m))
    check_results_for_IIS_CHPSTMGAS101_LB(results)


def test_datapackage_results_for_investment_var_outputs():
    datapackage_path = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "investment_var_output"
        / "datapackage.json"
    )
    es = EnergySystem.from_datapackage(
        str(datapackage_path), attributemap={}, typemap=TYPEMAP
    )

    m = Model(es)
    m.solve("cbc")

    results = processing.convert_keys_to_strings(processing.results(m))
    check_results_for_investment_var_output(results)
