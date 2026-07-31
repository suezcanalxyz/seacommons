import unreal


MAP_PACKAGE = "/Game/Maps/SeaCommonsOcean"
EXPECTED_LABELS = {
    "SC_Georeference",
    "SC_Sun",
    "SC_SkyAtmosphere",
    "SC_SkyLight",
    "SC_VolumetricCloud",
    "SC_HeightFog",
    "SC_WaterZone",
    "SC_WaterBodyOcean",
    "SC_AnonymousRaft",
    "SC_SeaCamera",
    "SC_PostProcess",
}


def fail(message):
    raise RuntimeError(f"[SeaCommonsValidation] {message}")


level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level_subsystem.load_level(MAP_PACKAGE):
    fail(f"Unable to load {MAP_PACKAGE}")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()
actors_by_label = {actor.get_actor_label(): actor for actor in actors}

missing = EXPECTED_LABELS.difference(actors_by_label)
if missing:
    fail(f"Missing actors: {', '.join(sorted(missing))}")

raft = actors_by_label["SC_AnonymousRaft"]
buoyancy_class = unreal.load_class(None, "/Script/Water.BuoyancyComponent")
buoyancy = raft.get_component_by_class(buoyancy_class)
if buoyancy is None:
    fail("Anonymous raft has no BuoyancyComponent")

buoyancy_data = buoyancy.get_editor_property("buoyancy_data")
pontoons = buoyancy_data.get_editor_property("pontoons")
if len(pontoons) != 4:
    fail(f"Expected 4 pontoons, found {len(pontoons)}")

ocean = actors_by_label["SC_WaterBodyOcean"]
water_component = ocean.get_water_body_component()
if water_component is None:
    fail("Ocean has no WaterBodyComponent")
if water_component.get_editor_property("water_material") is None:
    fail("Ocean has no water material")

georef = actors_by_label["SC_Georeference"]
origin = georef.get_origin_longitude_latitude_height()
if abs(origin.x - 15.0) > 0.001 or abs(origin.y - 35.0) > 0.001:
    fail(f"Unexpected Cesium origin: {origin}")

unreal.log(
    "[SeaCommonsValidation] PASS: "
    f"{len(EXPECTED_LABELS)} required actors, 4 pontoons, "
    "ocean material and Cesium origin verified"
)
