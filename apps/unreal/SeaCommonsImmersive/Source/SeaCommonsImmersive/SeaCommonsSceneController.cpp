#include "SeaCommonsSceneController.h"

#include "Dom/JsonObject.h"
#include "EngineUtils.h"
#include "GerstnerWaterWaves.h"
#include "HAL/PlatformFileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "PixelStreamingInputComponent.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "WaterBodyOceanActor.h"

DEFINE_LOG_CATEGORY_STATIC(LogSeaCommonsScene, Log, All);

ASeaCommonsSceneController::ASeaCommonsSceneController()
{
    PrimaryActorTick.bCanEverTick = false;
    PixelStreamingInput = CreateDefaultSubobject<UPixelStreamingInput>(
        TEXT("PixelStreamingInput")
    );
}

void ASeaCommonsSceneController::BeginPlay()
{
    Super::BeginPlay();
    PixelStreamingInput->OnInputEvent.AddDynamic(
        this,
        &ASeaCommonsSceneController::HandlePixelStreamingInput
    );
    LoadInitialScene();
}

bool ASeaCommonsSceneController::LoadInitialScene()
{
    FString ScenePath;
    const bool bHasCustomScene = FParse::Value(
        FCommandLine::Get(),
        TEXT("SeaCommonsScene="),
        ScenePath
    );
    if (!bHasCustomScene)
    {
        ScenePath = FPaths::ConvertRelativePathToFull(
            FPaths::Combine(
                FPaths::ProjectContentDir(),
                TEXT("Scenarios/demo-scene.json")
            )
        );
    }
    else if (FPaths::IsRelative(ScenePath))
    {
        ScenePath = FPaths::ConvertRelativePathToFull(
            FPaths::ProjectDir(),
            ScenePath
        );
    }

    FString SceneJson;
    if (!FFileHelper::LoadFileToString(SceneJson, *ScenePath))
    {
        UE_LOG(
            LogSeaCommonsScene,
            Warning,
            TEXT("No initial scene at %s; waiting for Pixel Streaming input."),
            *ScenePath
        );
        return false;
    }
    return ApplySceneJson(SceneJson);
}

void ASeaCommonsSceneController::HandlePixelStreamingInput(
    const FString& Descriptor
)
{
    TSharedPtr<FJsonObject> Envelope;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(
        Descriptor
    );
    if (!FJsonSerializer::Deserialize(Reader, Envelope) || !Envelope.IsValid())
    {
        return;
    }

    FString MessageType;
    if (
        Envelope->TryGetStringField(TEXT("type"), MessageType)
        && MessageType == TEXT("seacommons.scene")
    )
    {
        const TSharedPtr<FJsonObject>* Payload = nullptr;
        if (Envelope->TryGetObjectField(TEXT("payload"), Payload) && Payload)
        {
            FString SceneJson;
            const TSharedRef<TJsonWriter<>> Writer =
                TJsonWriterFactory<>::Create(&SceneJson);
            FJsonSerializer::Serialize(Payload->ToSharedRef(), Writer);
            ApplySceneJson(SceneJson);
        }
    }
}

bool ASeaCommonsSceneController::ApplySceneJson(const FString& SceneJson)
{
    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(
        SceneJson
    );
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        UE_LOG(LogSeaCommonsScene, Error, TEXT("Scene JSON is invalid."));
        return false;
    }

    FString SchemaVersion;
    if (
        !Root->TryGetStringField(TEXT("schema_version"), SchemaVersion)
        || SchemaVersion != TEXT("drift-scene/v1")
    )
    {
        UE_LOG(
            LogSeaCommonsScene,
            Error,
            TEXT("Unsupported scene schema: %s"),
            *SchemaVersion
        );
        return false;
    }
    if (!Root->TryGetStringField(TEXT("scenario_id"), ScenarioId))
    {
        UE_LOG(LogSeaCommonsScene, Error, TEXT("Scene has no scenario_id."));
        return false;
    }

    const TSharedPtr<FJsonObject>* Environment = nullptr;
    const TSharedPtr<FJsonObject>* Waves = nullptr;
    if (
        !Root->TryGetObjectField(TEXT("environment"), Environment)
        || !Environment
        || !(*Environment)->TryGetObjectField(TEXT("waves"), Waves)
        || !Waves
    )
    {
        UE_LOG(LogSeaCommonsScene, Error, TEXT("Scene has no wave state."));
        return false;
    }

    WaveState.SignificantHeightMetres = FMath::Max(
        0.0,
        (*Waves)->GetNumberField(TEXT("significant_height_m"))
    );
    WaveState.PeriodSeconds = FMath::Max(
        0.1,
        (*Waves)->GetNumberField(TEXT("period_s"))
    );
    WaveState.DirectionDegrees = FMath::Fmod(
        (*Waves)->GetNumberField(TEXT("direction_deg")) + 360.0,
        360.0
    );
    FString DirectionConvention;
    (*Waves)->TryGetStringField(
        TEXT("direction_convention"),
        DirectionConvention
    );
    WaveState.bDirectionIsFrom = DirectionConvention != TEXT("to");

    ConfigureOcean();
    PixelStreamingInput->SendPixelStreamingResponse(
        FString::Printf(
            TEXT("{\"type\":\"seacommons.scene.ready\",\"scenario_id\":\"%s\"}"),
            *ScenarioId
        )
    );
    UE_LOG(
        LogSeaCommonsScene,
        Log,
        TEXT("Applied %s: Hs %.2fm, T %.2fs, direction %.1f degrees."),
        *ScenarioId,
        WaveState.SignificantHeightMetres,
        WaveState.PeriodSeconds,
        WaveState.DirectionDegrees
    );
    return true;
}

AWaterBodyOcean* ASeaCommonsSceneController::ResolveOceanActor()
{
    if (IsValid(OceanActor))
    {
        return OceanActor;
    }
    for (TActorIterator<AWaterBodyOcean> It(GetWorld()); It; ++It)
    {
        OceanActor = *It;
        return OceanActor;
    }
    return nullptr;
}

void ASeaCommonsSceneController::ConfigureOcean()
{
    AWaterBodyOcean* Ocean = ResolveOceanActor();
    if (!Ocean)
    {
        UE_LOG(
            LogSeaCommonsScene,
            Warning,
            TEXT("Add one WaterBodyOcean to the level to render the sea.")
        );
        return;
    }

    RuntimeWaves = NewObject<UGerstnerWaterWaves>(
        Ocean,
        TEXT("SeaCommonsRuntimeWaves")
    );
    UGerstnerWaterWaveGeneratorSimple* Generator =
        NewObject<UGerstnerWaterWaveGeneratorSimple>(RuntimeWaves);

    // Deep-water dispersion: wavelength in metres is approximately 1.56*T^2.
    const float DominantWavelengthCm =
        100.0f * 1.56f * FMath::Square(WaveState.PeriodSeconds);
    const float SignificantHeightCm =
        100.0f * WaveState.SignificantHeightMetres;
    const float TravelDirection = FMath::Fmod(
        WaveState.DirectionDegrees
            + (WaveState.bDirectionIsFrom ? 180.0f : 0.0f),
        360.0f
    );

    Generator->NumWaves = 32;
    Generator->Seed = GetTypeHash(ScenarioId);
    Generator->Randomness = 0.35f;
    Generator->MinWavelength = FMath::Max(80.0f, DominantWavelengthCm * 0.18f);
    Generator->MaxWavelength = FMath::Max(
        Generator->MinWavelength + 1.0f,
        DominantWavelengthCm * 1.7f
    );
    Generator->WavelengthFalloff = 1.7f;
    Generator->MinAmplitude = FMath::Max(0.5f, SignificantHeightCm * 0.012f);
    Generator->MaxAmplitude = FMath::Max(
        Generator->MinAmplitude,
        SignificantHeightCm * 0.28f
    );
    Generator->AmplitudeFalloff = 1.55f;
    Generator->WindAngleDeg = TravelDirection > 180.0f
        ? TravelDirection - 360.0f
        : TravelDirection;
    Generator->DirectionAngularSpreadDeg = 26.0f;
    Generator->SmallWaveSteepness = FMath::Clamp(
        0.28f + WaveState.SignificantHeightMetres * 0.035f,
        0.28f,
        0.56f
    );
    Generator->LargeWaveSteepness = FMath::Clamp(
        0.12f + WaveState.SignificantHeightMetres * 0.025f,
        0.12f,
        0.34f
    );
    Generator->SteepnessFalloff = 1.2f;

    RuntimeWaves->GerstnerWaveGenerator = Generator;
    RuntimeWaves->RecomputeWaves(false);
    Ocean->SetWaterWaves(RuntimeWaves);
}
