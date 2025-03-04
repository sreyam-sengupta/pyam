import pytest
import re

import numpy as np
import pandas as pd
from pyam import check_aggregate, IamDataFrame
from pyam.utils import IAMC_IDX
from pyam.testing import assert_iamframe_equal

from .conftest import DTS_MAPPING

LONG_IDX = IAMC_IDX + ["year"]

PE_MAX_DF = pd.DataFrame(
    [
        ["model_a", "scen_a", "World", "Primary Energy", "EJ/yr", 2005, 9.0],
        ["model_a", "scen_a", "World", "Primary Energy", "EJ/yr", 2010, 10.0],
        ["model_a", "scen_a", "reg_a", "Primary Energy", "EJ/yr", 2005, 6.0],
        ["model_a", "scen_a", "reg_a", "Primary Energy", "EJ/yr", 2010, 6.0],
        ["model_a", "scen_a", "reg_b", "Primary Energy", "EJ/yr", 2005, 3.0],
        ["model_a", "scen_a", "reg_b", "Primary Energy", "EJ/yr", 2010, 4.0],
    ],
    columns=LONG_IDX + ["value"],
)

CO2_MAX_DF = pd.DataFrame(
    [
        ["model_a", "scen_a", "World", "Emissions|CO2", "EJ/yr", 2005, 6.0],
        ["model_a", "scen_a", "World", "Emissions|CO2", "EJ/yr", 2010, 8.0],
        ["model_a", "scen_a", "reg_a", "Emissions|CO2", "EJ/yr", 2005, 4.0],
        ["model_a", "scen_a", "reg_a", "Emissions|CO2", "EJ/yr", 2010, 5.0],
        ["model_a", "scen_a", "reg_b", "Emissions|CO2", "EJ/yr", 2005, 2.0],
        ["model_a", "scen_a", "reg_b", "Emissions|CO2", "EJ/yr", 2010, 3.0],
    ],
    columns=LONG_IDX + ["value"],
)

PRICE_MAX_DF = pd.DataFrame(
    [
        ["model_a", "scen_a", "World", "Price|Carbon", "USD/tCO2", 2005, 10.0],
        ["model_a", "scen_a", "World", "Price|Carbon", "USD/tCO2", 2010, 30.0],
    ],
    columns=LONG_IDX + ["value"],
)


@pytest.mark.parametrize(
    "variable,data",
    (
        ("Primary Energy", PE_MAX_DF),
        (["Primary Energy", "Emissions|CO2"], pd.concat([PE_MAX_DF, CO2_MAX_DF])),
    ),
)
def test_aggregate(simple_df, variable, data):
    # check that `variable` is a a direct sum and matches given total
    exp = simple_df.filter(variable=variable)
    assert_iamframe_equal(simple_df.aggregate(variable), exp)

    # use other method (max) both as string and passing the function
    _df = data.copy()
    if simple_df.time_col == "time":
        _df.year = _df.year.replace(DTS_MAPPING)
        _df.rename({"year": "time"}, axis="columns", inplace=True)
    exp = IamDataFrame(_df, meta=simple_df.meta)
    for m in ["max", np.max]:
        assert_iamframe_equal(simple_df.aggregate(variable, method=m), exp)


def test_check_aggregate(simple_df):
    # assert that `check_aggregate` returns None for full data
    assert simple_df.check_aggregate("Primary Energy") is None

    # assert that `check_aggregate` returns non-matching data
    obs = simple_df.filter(
        variable="Primary Energy|Coal", region="World", keep=False
    ).check_aggregate("Primary Energy")
    exp = pd.DataFrame([[12.0, 3.0], [15.0, 5.0]])
    np.testing.assert_array_equal(obs.values, exp.values)


def test_check_aggregate_top_level(simple_df):
    # assert that `check_aggregate` returns None for full data
    assert check_aggregate(simple_df, variable="Primary Energy", year=2005) is None

    # duplicate scenario, assert `check_aggregate` returns non-matching data
    _df = simple_df.rename(scenario={"scen_a": "foo"}, append=True).filter(
        scenario="foo", variable="Primary Energy|Coal", keep=False
    )

    obs = check_aggregate(
        _df, variable="Primary Energy", year=2005, exclude_on_fail=True
    )
    exp = pd.DataFrame([[12.0, 3.0], [8.0, 2.0], [4.0, 1.0]])
    np.testing.assert_array_equal(obs.values, exp.values)

    # assert that scenario `foo` has correctly been assigned as `exclude=True`
    np.testing.assert_array_equal(_df.exclude, [True, False])


@pytest.mark.parametrize(
    "variable", ("Primary Energy", (["Primary Energy", "Emissions|CO2"]))
)
def test_aggregate_append(simple_df, variable):
    # remove `variable`, do aggregate and append, check equality to original
    _df = simple_df.filter(variable=variable, keep=False)
    _df.aggregate(variable, append=True)
    assert_iamframe_equal(_df, simple_df)


def test_aggregate_with_components(simple_df):
    # rename sub-category to test setting components explicitly as list
    df = simple_df.rename(variable={"Primary Energy|Wind": "foo"})
    assert df.check_aggregate("Primary Energy") is not None
    components = ["Primary Energy|Coal", "foo"]
    assert df.check_aggregate("Primary Energy", components=components) is None


def test_aggregate_by_list_with_components_raises(simple_df):
    # using list of variables and components raises an error
    v = ["Primary Energy", "Emissions|CO2"]
    components = ["Primary Energy|Coal", "Primary Energy|Wind"]
    with pytest.raises(NotImplementedError, match="Aggregating by list of variables"):
        simple_df.aggregate(v, components=components)


def test_aggregate_recursive(recursive_df):
    # use the feature `recursive=True`

    # create object without variables to be aggregated
    v = "Secondary Energy|Electricity"
    agg_vars = [f"{v}{i}" for i in ["", "|Wind"]]
    df_minimal = recursive_df.filter(variable=agg_vars, keep=False)

    # return recursively aggregated data as new object
    obs = df_minimal.aggregate(variable=v, recursive=True)
    assert_iamframe_equal(obs, recursive_df.filter(variable=agg_vars))

    # append to `self`
    df_minimal.aggregate(variable=v, recursive=True, append=True)
    assert_iamframe_equal(df_minimal, recursive_df)


def test_aggregate_skip_intermediate(recursive_df):
    # make the data inconsistent, check (and then skip) validation

    recursive_df._data.iloc[0] = recursive_df._data.iloc[0] + 2
    recursive_df._data.iloc[3] = recursive_df._data.iloc[3] + 2

    # create object without variables to be aggregated, but with intermediate variables
    v = "Secondary Energy|Electricity"
    df_minimal = recursive_df.filter(variable=v, scenario="scen_a", keep=False)
    agg_vars = [f"{v}{i}" for i in ["", "|Wind"]]
    df_minimal.filter(variable=agg_vars, scenario="scen_b", keep=False, inplace=True)

    # simply calling recursive aggregation raises an error
    match = "Aggregated values are inconsistent with existing data:"
    with pytest.raises(ValueError, match=match):
        df_minimal.aggregate(variable=v, recursive=True, append=True)

    # append to `self` with skipping validation
    df_minimal.aggregate(variable=v, recursive="skip-validate", append=True)
    assert_iamframe_equal(df_minimal, recursive_df)


@pytest.mark.parametrize(
    "variable, append", (("Primary Energy|Coal", "foo"), (False, True))
)
def test_aggregate_empty(test_df, variable, append, caplog):
    """Check for performing an "empty" aggregation"""

    if append:
        # with `append=True`, the instance is unchanged
        obs = test_df.copy()
        obs.aggregate(variable, append=True)
        assert_iamframe_equal(test_df, obs)
    else:
        # with `append=False` (default), an empty instance is returned
        assert test_df.aggregate(variable).empty

    msg = f"Cannot aggregate variable '{variable}' because it has no components."
    idx = caplog.messages.index(msg)
    assert caplog.records[idx].levelname == "INFO"


def test_aggregate_unknown_method(simple_df):
    """Check that using unknown string as method raises an error"""
    pytest.raises(ValueError, simple_df.aggregate, "Primary Energy", method="foo")


def test_aggregate_components_as_dict(simple_df):
    """Check that using a dictionary as `componenents` raises an error"""
    with pytest.raises(ValueError, match="Value for `components` must be a list"):
        simple_df.aggregate("Primary Energy", components={"Primary Energy|Coal": "foo"})


@pytest.mark.parametrize(
    "variable",
    (
        "Primary Energy",
        (["Primary Energy", "Primary Energy|Coal", "Primary Energy|Wind"]),
    ),
)
def test_aggregate_region(simple_df, variable):
    # check that `variable` is a a direct sum across regions
    exp = simple_df.filter(variable=variable, region="World")
    assert_iamframe_equal(simple_df.aggregate_region(variable), exp)

    # check custom `region` (will include `World`, so double-count values)
    foo = exp.rename(region={"World": "foo"})
    foo._data = foo._data * 2
    assert_iamframe_equal(simple_df.aggregate_region(variable, region="foo"), foo)


def test_check_aggregate_region(simple_df):
    # assert that `check_aggregate_region` returns None for full data
    assert simple_df.check_aggregate_region("Primary Energy") is None

    # assert that `check_aggregate_region` returns non-matching data
    obs = simple_df.filter(
        variable="Primary Energy", region="reg_a", keep=False
    ).check_aggregate_region("Primary Energy")
    exp = pd.DataFrame([[12.0, 4.0], [15.0, 6.0]])
    np.testing.assert_array_equal(obs.values, exp.values)


def test_check_aggregate_region_log(simple_df, caplog):
    # verify that `check_aggregate_region()` writes log on empty assertion
    (
        simple_df.filter(
            variable="Primary Energy", region="World", keep=False
        ).check_aggregate_region("Primary Energy")
    )
    msg = "Variable 'Primary Energy' does not exist in region 'World'."
    idx = caplog.messages.index(msg)
    assert caplog.records[idx].levelname == "INFO"


@pytest.mark.parametrize(
    "variable",
    (
        "Primary Energy",
        (["Primary Energy", "Primary Energy|Coal", "Primary Energy|Wind"]),
    ),
)
def test_aggregate_region_append(simple_df, variable):
    # remove `variable`, aggregate and append, check equality to original
    _df = simple_df.filter(variable=variable, region="World", keep=False)
    _df.aggregate_region(variable, append=True)
    assert_iamframe_equal(_df, simple_df)


@pytest.mark.parametrize(
    "variable",
    (
        "Primary Energy",
        (["Primary Energy", "Primary Energy|Coal", "Primary Energy|Wind"]),
    ),
)
def test_aggregate_region_with_subregions(simple_df, variable):
    # check that custom `subregions` works (assumes only `reg_a` is in `World`)
    exp = simple_df.filter(variable=variable, region="reg_a").rename(
        region={"reg_a": "World"}
    )
    obs = simple_df.aggregate_region(variable, subregions="reg_a")
    assert_iamframe_equal(obs, exp)

    # check that both custom `region` and `subregions` work
    foo = exp.rename(region={"World": "foo"})
    obs = simple_df.aggregate_region(variable, region="foo", subregions="reg_a")
    assert_iamframe_equal(obs, foo)

    # check that invalid list of subregions returns empty
    assert simple_df.aggregate_region(variable, subregions=["reg_c"]).empty


@pytest.mark.parametrize(
    "variable,data",
    (
        ("Price|Carbon", PRICE_MAX_DF),
        (["Price|Carbon", "Emissions|CO2"], pd.concat([PRICE_MAX_DF, CO2_MAX_DF])),
    ),
)
def test_aggregate_region_with_other_method(simple_df, variable, data):
    # use other method (max) both as string and passing the function
    _df = data.copy()
    if simple_df.time_col == "time":
        _df.year = _df.year.replace(DTS_MAPPING)
        _df.rename({"year": "time"}, axis="columns", inplace=True)

    exp = IamDataFrame(_df, meta=simple_df.meta).filter(region="World")
    for m in ["max", np.max]:
        obs = simple_df.aggregate_region(variable, method=m)
        assert_iamframe_equal(obs, exp)


def test_aggregate_region_with_components(simple_df):
    # CO2 emissions have "bunkers" only defined at the region level
    v = "Emissions|CO2"
    assert simple_df.check_aggregate_region(v) is not None
    assert simple_df.check_aggregate_region(v, components=True) is None

    # rename emissions of bunker to test setting components as list
    _df = simple_df.rename(variable={"Emissions|CO2|Bunkers": "foo"})
    assert _df.check_aggregate_region(v, components=["foo"]) is None


def test_aggregate_region_with_weights(simple_df, caplog):
    # carbon price shouldn't be summed but be weighted by emissions
    v = "Price|Carbon"
    w = "Emissions|CO2"
    assert simple_df.check_aggregate_region(v) is not None
    assert simple_df.check_aggregate_region(v, weight=w) is None

    # test the full dataset
    exp = simple_df.filter(variable=v, region="World")
    assert_iamframe_equal(simple_df.aggregate_region(v, weight=w), exp)


def test_aggregate_region_with_negative_weights(simple_df, caplog):
    # carbon price shouldn't be summed but be weighted by emissions
    v = "Price|Carbon"
    w = "Emissions|CO2"

    # dropping negative weights works as expected
    neg_weights_df = simple_df.copy()
    neg_weights_df._data[18] = -6
    exp = simple_df.filter(variable=v, region="World", year=2010)
    assert_iamframe_equal(neg_weights_df.aggregate_region(v, weight=w), exp)

    msg = (
        "Some weights are negative. Data weighted by negative values will be dropped. "
        "To use both positive and negative weights, please use the keyword argument "
        "`drop_negative_weights=False`."
    )
    idx = caplog.messages.index(msg)
    assert caplog.records[idx].levelname == "WARNING"

    # *not* dropping negative weights works as expected
    exp = simple_df.filter(variable=v, region="World")
    exp._data[0] = -8
    assert_iamframe_equal(
        neg_weights_df.aggregate_region(v, weight=w, drop_negative_weights=False), exp
    )


@pytest.mark.parametrize(
    "filter_arg,log_message",
    (
        (dict(year=2010), ""),
        (dict(), "model_a   scen_a  reg_b  2005\n1  "),
    ),
)
def test_aggregate_region_with_weights_inconsistent_index(
    simple_df, caplog, filter_arg, log_message
):
    # carbon price shouldn't be summed but be weighted by emissions
    v = "Price|Carbon"
    w = "Emissions|CO2"

    log_message = "\n0  " + log_message + "model_a   scen_a  reg_b  2010"
    if simple_df.time_domain == "datetime":
        time_col = "     time"
        log_message = log_message.replace(" 2005", "2005-06-17").replace(
            " 2010", "2010-07-21"
        )
    else:
        time_col = "year"

    # missing weight row raises an error
    _df = simple_df.filter(variable=w, region="reg_b", keep=False, **filter_arg)
    match = r"Missing weights for the following data.*\n.*" + re.escape(log_message)
    with pytest.raises(ValueError, match=match):
        _df.aggregate_region(v, weight=w)

    # missing data row prints a warning (data-index is a subset of weight-index)
    exp = simple_df.filter(variable=v, region="World")
    if not filter_arg:
        exp._data[0] = 1.0
    exp._data[1] = 30.0
    _df = simple_df.filter(variable=v, region="reg_b", keep=False, **filter_arg)
    assert_iamframe_equal(_df.aggregate_region(v, weight=w), exp)

    msg = (
        "Ignoring weights for the following missing data rows:\n"
        f"     model scenario region  {time_col}" + log_message
    )

    idx = caplog.messages.index(msg)
    assert caplog.records[idx].levelname == "WARNING"


def test_aggregate_region_with_weights_raises(simple_df):
    # carbon price shouldn't be summed but be weighted by emissions
    v = "Price|Carbon"
    w = "Emissions|CO2"

    # using weight and method other than 'sum' raises an error
    pytest.raises(ValueError, simple_df.aggregate_region, v, method="max", weight="bar")

    # setting both weight and components raises an error
    pytest.raises(
        ValueError, simple_df.aggregate_region, v, components=True, weight="bar"
    )

    # dropping negative weights can only be used with weight
    pytest.raises(
        ValueError, simple_df.aggregate_region, v, drop_negative_weights=False
    )


@pytest.mark.parametrize("variable, append", (("Primary Energy", "foo"), (False, True)))
def test_aggregate_region_empty(test_df, variable, append, caplog):
    """Check for performing an "empty" aggregation"""

    if append:
        # with `append=True`, the instance is unchanged
        obs = test_df.copy()
        obs.aggregate_region(variable, append=True)
        assert_iamframe_equal(test_df, obs)

    else:
        # with `append=False` (default), an empty instance is returned
        assert test_df.aggregate_region(variable).empty

    msg = (
        f"Cannot aggregate variable '{variable}' to 'World' "
        "because it does not exist in any subregion."
    )
    idx = caplog.messages.index(msg)
    assert caplog.records[idx].levelname == "INFO"


def test_aggregate_region_unknown_method(simple_df):
    # using unknown string as method raises an error
    v = "Emissions|CO2"
    pytest.raises(ValueError, simple_df.aggregate_region, v, method="foo")


@pytest.mark.parametrize(
    "variable",
    (
        "Primary Energy",
        ["Primary Energy", "Primary Energy|Coal"],
    ),
)
def test_aggregate_time(subannual_df, variable):
    # check that `variable` is a a direct sum and matches given total
    exp = subannual_df.filter(variable=variable, subannual=["year"])
    assert_iamframe_equal(subannual_df.aggregate_time(variable), exp)


def test_check_internal_consistency(simple_df):
    _df = simple_df.filter(variable="Price|Carbon", keep=False)

    # assert that test data is consistent (except for `Price|Carbon`)
    assert _df.check_internal_consistency(components=True) is None

    # assert removing a specific subsector causes inconsistencies
    obs = _df.filter(
        variable="Primary Energy|Coal", region="reg_a", keep=False
    ).check_internal_consistency(components=True)

    # test reported inconsistency
    exp = pd.DataFrame(
        [
            [np.nan, np.nan, 9.0, 3.0],
            [np.nan, np.nan, 10.0, 4.0],
            [8.0, 2.0, np.nan, np.nan],
            [9.0, 3.0, np.nan, np.nan],
        ]
    )
    np.testing.assert_array_equal(obs.values, exp.values)
