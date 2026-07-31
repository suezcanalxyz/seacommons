#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SeaCommonsSceneController.generated.h"

class AWaterBodyOcean;
class UPixelStreamingInput;
class UGerstnerWaterWaves;

USTRUCT(BlueprintType)
struct FSeaCommonsWaveState
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Ocean")
    float SignificantHeightMetres = 0.65f;

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Ocean")
    float PeriodSeconds = 5.5f;

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Ocean")
    float DirectionDegrees = 285.0f;

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Ocean")
    bool bDirectionIsFrom = true;
};

/**
 * Renderer adapter for drift-scene/v1.
 *
 * Horizontal positions remain authoritative API data. Wave motion generated
 * here is visual until a validated six-degree vessel model is introduced.
 */
UCLASS(Blueprintable)
class SEACOMMONSIMMERSIVE_API ASeaCommonsSceneController : public AActor
{
    GENERATED_BODY()

public:
    ASeaCommonsSceneController();

    UFUNCTION(BlueprintCallable, Category = "SeaCommons|Scene")
    bool ApplySceneJson(const FString& SceneJson);

    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category = "SeaCommons|Ocean")
    TObjectPtr<AWaterBodyOcean> OceanActor;

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Scene")
    FString ScenarioId;

    UPROPERTY(BlueprintReadOnly, Category = "SeaCommons|Ocean")
    FSeaCommonsWaveState WaveState;

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UPixelStreamingInput> PixelStreamingInput;

    UPROPERTY(Transient)
    TObjectPtr<UGerstnerWaterWaves> RuntimeWaves;

    UFUNCTION()
    void HandlePixelStreamingInput(const FString& Descriptor);

    bool LoadInitialScene();
    void ConfigureOcean();
    AWaterBodyOcean* ResolveOceanActor();
};

