from Navigation_Bot.bots.route_info_parser import RouteInfoParser


def test_route_info_parser_parses_date_time_and_address():
    parser = RouteInfoParser()

    result = parser.parse(
        "Погрузка: 04.07.2026, прибыть к 8:00:00, г. Новосибирск, ул. Станционная, 80",
        "Погрузка",
    )

    assert result[0]["Погрузка 1"] == "г. Новосибирск, ул. Станционная, 80"
    assert result[0]["Дата 1"] == "04.07.2026"
    assert result[0]["Время 1"] == "08:00"


def test_route_info_parser_parses_numbered_points_and_comment():
    parser = RouteInfoParser()

    result = parser.parse(
        "Погрузка:\n"
        "1) г. Москва, ул. Ленина, 1; Комментарий: ворота 3\n"
        "2) Московская область, г. Химки, ул. Заводская, 2",
        "Погрузка",
    )

    assert result[0]["Погрузка 1"] == "г. Москва, ул. Ленина, 1"
    assert result[0]["Дата 1"] == "Не указано"
    assert result[0]["Время 1"] == "Не указано"
    assert result[1]["Погрузка 2"] == "Московская область, г. Химки, ул. Заводская, 2"
    assert result[2]["Комментарий"] == "Комментарий: ворота 3"


def test_route_info_parser_does_not_use_phone_fragment_as_time():
    parser = RouteInfoParser()

    result = parser.parse(
        "Погрузка:\n"
        "1) г. Москва, ул. Ленина, 1; тел. +7 999 111-22-33",
        "Погрузка",
    )

    assert result[0]["Погрузка 1"] == "г. Москва, ул. Ленина, 1"
    assert result[0]["Время 1"] == "Не указано"
    assert result[1]["Комментарий"] == "тел. +7 999 111-22-33"


def test_route_info_parser_moves_company_prefix_to_comment_before_address():
    parser = RouteInfoParser()

    result = parser.parse(
        'Разгрузка: 07.07.2026, прибыть к 16:00:00. '
        'ООО "ЛОРЕНЦ СНЭК-УОРЛД РАША", ООО "Кюне-Нагель" '
        'Московская обл,Раменский р-он, с.п.Софьинское,Промзона "ССТ",корпус 1,секция 978',
        "Выгрузка",
    )

    assert result[0]["Выгрузка 1"] == (
        'Московская обл,Раменский р-он, с.п.Софьинское,Промзона "ССТ",корпус 1,секция 978'
    )
    assert result[0]["Дата 1"] == "07.07.2026"
    assert result[0]["Время 1"] == "16:00"
    assert result[1]["Комментарий"] == 'ООО "ЛОРЕНЦ СНЭК-УОРЛД РАША", ООО "Кюне-Нагель"'
