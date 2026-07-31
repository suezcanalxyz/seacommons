import unreal


MAP_PACKAGE = "/Game/Maps/SeaCommonsOcean"
GENERATED_TAG = "SeaCommonsGenerated"


def log(message):
    unreal.log(f"[SeaCommonsLevel] {message}")


def warn(message):
    unreal.log_warning(f"[SeaCommonsLevel] {message}")


def load_class(path):
    actor_class = unreal.load_class(None, path)
    if actor_class is None:
        raise RuntimeError(f"Unable to load actor class {path}")
    return actor_class


def spawn(actor_class, label, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        actor_class,
        unreal.Vector(*location),
        unreal.Rotator(*rotation),
    )
    if actor is None:
        raise RuntimeError(f"Unable to spawn {label}")
    actor.set_actor_label(label)
    actor.tags = [GENERATED_TAG]
    return actor


def set_if_possible(target, property_name, value):
    try:
        target.set_editor_property(property_name, value)
        return True
    except Exception as exc:
        warn(f"{target.get_name()}.{property_name}: {exc}")
        return False


def component(actor, class_path):
    component_class = unreal.load_class(None, class_path)
    return actor.get_component_by_class(component_class) if component_class else None


def configure_georeference():
    georef = spawn(
        load_class("/Script/CesiumRuntime.CesiumGeoreference"),
        "SC_Georeference",
    )
    try:
        georef.set_origin_longitude_latitude_height(
            unreal.Vector(15.0, 35.0, 0.0)
        )
    except Exception as exc:
        warn(f"Cesium origin method unavailable: {exc}")
        set_if_possible(georef, "origin_longitude", 15.0)
        set_if_possible(georef, "origin_latitude", 35.0)
        set_if_possible(georef, "origin_height", 0.0)
    return georef


def configure_lighting():
    sun = spawn(
        unreal.DirectionalLight,
        "SC_Sun",
        rotation=(-32.0, -24.0, 0.0),
    )
    sun_component = component(
        sun,
        "/Script/Engine.DirectionalLightComponent",
    )
    if sun_component:
        set_if_possible(sun_component, "intensity", 8.0)
        set_if_possible(sun_component, "atmosphere_sun_light", True)
        set_if_possible(sun_component, "cast_cloud_shadows", True)

    sky = spawn(unreal.SkyAtmosphere, "SC_SkyAtmosphere")
    sky_light = spawn(unreal.SkyLight, "SC_SkyLight")
    sky_light_component = component(sky_light, "/Script/Engine.SkyLightComponent")
    if sky_light_component:
        set_if_possible(sky_light_component, "mobility", unreal.ComponentMobility.MOVABLE)
        set_if_possible(sky_light_component, "real_time_capture", True)
        set_if_possible(sky_light_component, "intensity", 0.75)

    clouds = spawn(unreal.VolumetricCloud, "SC_VolumetricCloud", location=(0.0, 0.0, 65000.0))
    fog = spawn(unreal.ExponentialHeightFog, "SC_HeightFog")
    fog_component = component(fog, "/Script/Engine.ExponentialHeightFogComponent")
    if fog_component:
        set_if_possible(fog_component, "fog_density", 0.012)
        set_if_possible(fog_component, "fog_height_falloff", 0.18)
        fog_component.set_volumetric_fog(True)
        fog_component.set_volumetric_fog_distance(200000.0)

    return [sun, sky, sky_light, clouds, fog]


def configure_ocean():
    zone = spawn(
        load_class("/Script/Water.WaterZone"),
        "SC_WaterZone",
    )
    set_if_possible(zone, "zone_extent", unreal.Vector2D(200000.0, 200000.0))

    ocean = spawn(
        load_class("/Script/Water.WaterBodyOcean"),
        "SC_WaterBodyOcean",
        location=(0.0, 0.0, 0.0),
    )
    water_component = ocean.get_water_body_component()
    ocean_material = unreal.load_asset(
        "/Water/Materials/WaterSurface/Water_Material_Ocean"
    )
    if water_component and ocean_material:
        set_if_possible(water_component, "water_material", ocean_material)
        set_if_possible(water_component, "target_wave_mask_depth", 5000.0)
    return zone, ocean


def configure_subject_and_camera():
    raft = spawn(
        load_class("/Script/SeaCommonsImmersive.SeaCommonsRaft"),
        "SC_AnonymousRaft",
        location=(0.0, 0.0, 180.0),
        rotation=(0.0, 18.0, 0.0),
    )

    camera = spawn(
        unreal.CineCameraActor,
        "SC_SeaCamera",
        location=(-2400.0, -1700.0, 1050.0),
        rotation=(-14.0, 35.0, 0.0),
    )
    cine_component = camera.get_cine_camera_component()
    set_if_possible(cine_component, "current_focal_length", 32.0)
    set_if_possible(cine_component, "current_aperture", 5.6)
    return raft, camera


def configure_post_process():
    volume = spawn(unreal.PostProcessVolume, "SC_PostProcess")
    set_if_possible(volume, "unbound", True)
    settings = volume.get_editor_property("settings")
    set_if_possible(settings, "override_color_saturation", True)
    set_if_possible(settings, "color_saturation", unreal.Vector4(0.92, 0.98, 1.02, 1.0))
    set_if_possible(settings, "override_vignette_intensity", True)
    set_if_possible(settings, "vignette_intensity", 0.18)
    volume.set_editor_property("settings", settings)
    return volume


def build_level():
    log(f"Creating {MAP_PACKAGE}")
    level_subsystem = unreal.get_editor_subsystem(
        unreal.LevelEditorSubsystem
    )
    if not level_subsystem.new_level(MAP_PACKAGE):
        raise RuntimeError(f"Unable to create {MAP_PACKAGE}")

    configure_georeference()
    configure_lighting()
    configure_ocean()
    configure_subject_and_camera()
    configure_post_process()

    editor_subsystem = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem
    )
    world = editor_subsystem.get_editor_world()
    world_settings = world.get_world_settings()
    game_mode = load_class(
        "/Script/SeaCommonsImmersive.SeaCommonsImmersiveGameMode"
    )
    set_if_possible(world_settings, "default_game_mode", game_mode)

    if not level_subsystem.save_current_level():
        raise RuntimeError("Failed to save the ocean level")
    unreal.EditorAssetLibrary.save_directory("/Game/Maps", only_if_is_dirty=False, recursive=True)
    log("Ocean level saved successfully")


build_level()
